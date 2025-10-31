# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, shutil, math

app = FastAPI()

# ===== CORS - عدل النطاقات حسب مكان نشر الواجهة =====
origins = [
    "http://localhost:5173",
    "https://perfume-label-frontend.vercel.app",
    # أضف هنا رابط الواجهة المنشور (مثلاً Vercel) إن لزم
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== ثابت التحويل mm -> points (ReportLab uses points) =====
MM_TO_PT = 2.83465

def mm_to_pt(mm: float) -> float:
    return float(mm) * MM_TO_PT

# ===== مسارات الملفات الثابتة =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_PDF = os.path.join(BASE_DIR, "labels.pdf")
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
AMIRI_TTF = os.path.join(BASE_DIR, "Amiri-Regular.ttf")  # ضع هذا الملف إن أردت دعم عربي جميل

# تسجيل خط Amiri إن وجد
ARABIC_FONT = None
if os.path.exists(AMIRI_TTF):
    try:
        pdfmetrics.registerFont(TTFont("Amiri", AMIRI_TTF))
        ARABIC_FONT = "Amiri"
        print("✅ Amiri font registered.")
    except Exception as e:
        print("⚠️ Failed to register Amiri:", e)

# ===== نماذج البيانات المتوقعة من الواجهة =====
class TemplateItem(BaseModel):
    perfumeName: str
    price: Optional[str] = ""
    multiplier: Optional[str] = ""
    shopName: Optional[str] = None
    # يمكنك لاحقًا إضافة extra_fields لكل قالب

    @validator("price")
    def price_must_be_digits(cls, v):
        if not v or v == "":
            return v
        cleaned = v.replace(" ", "").replace(",", "")
        if not cleaned.isdigit():
            raise ValueError("price must contain digits only")
        return v

    @validator("multiplier")
    def multiplier_must_be_digits(cls, v):
        if not v or v == "":
            return v
        cleaned = v.replace(" ", "").replace("×", "").replace("x", "")
        if not cleaned.isdigit():
            raise ValueError("multiplier must contain digits only")
        return v

class FontSettings(BaseModel):
    perfumeFont: Optional[str] = "Helvetica-Bold"
    perfumeSize: int = 12
    shopFont: Optional[str] = "Times-Italic"
    shopSize: int = 10
    priceFont: Optional[str] = "Helvetica-Bold"
    priceSize: int = 9
    quantityFont: Optional[str] = "Helvetica"
    quantitySize: int = 9

class GenerateRequest(BaseModel):
    perfumeName: Optional[str] = None        # عام (يمكن تجاوزه بقالب)
    shopName: Optional[str] = None
    price: Optional[str] = ""
    quantity: Optional[str] = ""
    copies: int = Field(1, ge=1, le=35)
    labelWidth: float = Field(40.0, gt=0)    # بالـ mm من الواجهة
    labelHeight: float = Field(40.0, gt=0)
    borderRadius: float = Field(2.0, ge=0)  # بالـ mm
    fontSettings: Optional[FontSettings] = FontSettings()
    templates: Optional[List[TemplateItem]] = None

    @validator("labelWidth")
    def width_fits_a4(cls, v):
        page_w_mm = A4[0] / MM_TO_PT
        if v > page_w_mm:
            raise ValueError(f"label width must be <= page width ({page_w_mm:.1f} mm)")
        return v

    @validator("labelHeight")
    def height_fits_a4(cls, v):
        page_h_mm = A4[1] / MM_TO_PT
        if v > page_h_mm:
            raise ValueError(f"label height must be <= page height ({page_h_mm:.1f} mm)")
        return v

# ===== endpoint لرفع لوجو جديد (logo.png سيُستخدم تلقائياً) =====
@app.post("/upload_logo")
async def upload_logo(file: UploadFile = File(...)):
    try:
        with open(LOGO_PATH, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return {"message": "Logo uploaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== توليد PDF =====
@app.post("/generate_label")
def generate_label(req: GenerateRequest):
    try:
        # تحقق من وجود قوالب
        if not req.templates or len(req.templates) == 0:
            raise HTTPException(status_code=400, detail="templates list is required and must contain at least one item")

        # حساب الوحدات بالـ points
        label_w_pt = mm_to_pt(req.labelWidth)
        label_h_pt = mm_to_pt(req.labelHeight)
        radius_pt = mm_to_pt(req.borderRadius)

        page_w_pt, page_h_pt = A4
        margin = 10  # نقطة كهوامش ثابتة

        # حساب الأعمدة/الصفوف الممكنة على صفحة A4
        cols = max(1, int((page_w_pt - margin) // label_w_pt))
        rows = max(1, int((page_h_pt - margin) // label_h_pt))
        max_labels_per_page = cols * rows

        # تجهيز قائمة الملصقات (templates) بحيث تُكرَّر حتى يصل العدد المطلوب copies
        desired = []
        idx = 0
        while len(desired) < req.copies:
            tpl = req.templates[idx % len(req.templates)]
            desired.append(tpl)
            idx += 1

        # نقطع إلى ما يمكن وضعه على صفحة واحدة (يمكن لاحقًا إضافة صفحات متعددة)
        to_generate = min(len(desired), max_labels_per_page)

        # تحميل اللوجو إن وُجد
        logo = ImageReader(LOGO_PATH) if os.path.exists(LOGO_PATH) else None

        # إنشاء canvas
        c = canvas.Canvas(OUT_PDF, pagesize=A4)

        # دالة دعم اكتشاف العربية (مبسيط)
        def contains_arabic(s: str) -> bool:
            if not s:
                return False
            for ch in s:
                if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F":
                    return True
            return False

        # رسم ملصق واحد
        def draw_label(x, y, tpl: TemplateItem):
            # إطار خارجي بزوايا دائرية (radius_pt)
            c.setLineWidth(0.9)
            c.setStrokeColor(colors.black)
            c.roundRect(x + 3, y + 3, label_w_pt - 6, label_h_pt - 6, radius_pt, stroke=1, fill=0)

            # رسم اللوجو مركزًا في الأعلى (إن وُجد)
            if logo:
                # نضع اللوجو بأقصى عرض 40% من الملصق أو 30 نقطة (قيمة افتراضية يمكن تطويرها)
                logo_w = min(label_w_pt * 0.45, 60)
                logo_h = logo_w
                c.drawImage(logo, x + (label_w_pt - logo_w) / 2, y + label_h_pt - logo_h - 8, logo_w, logo_h, mask='auto')

            # اسم العطر (من القالب أولاً ثم من العام)
            pname = tpl.perfumeName if tpl.perfumeName else (req.perfumeName or "")
            # اختيار الخط المناسب (إن كان عربي استخدم Amiri إن متاح)
            fs = req.fontSettings or FontSettings()
            try:
                if contains_arabic(pname) and ARABIC_FONT:
                    c.setFont(ARABIC_FONT, fs.perfumeSize)
                else:
                    c.setFont(fs.perfumeFont or "Helvetica-Bold", fs.perfumeSize)
            except Exception:
                c.setFont("Helvetica-Bold", fs.perfumeSize)
            c.drawCentredString(x + label_w_pt / 2, y + label_h_pt / 2 + fs.perfumeSize/1.5 + 6, pname)

            # اسم المحل (template يمكن أن يحتوي shopName)
            shop_text = tpl.shopName if tpl.shopName else (req.shopName or "")
            try:
                if contains_arabic(shop_text) and ARABIC_FONT:
                    c.setFont(ARABIC_FONT, fs.shopSize)
                else:
                    c.setFont(fs.shopFont or "Times-Italic", fs.shopSize)
            except Exception:
                c.setFont("Times-Italic", fs.shopSize)
            c.drawCentredString(x + label_w_pt / 2, y + label_h_pt / 2 - fs.shopSize/1.5 - 2, shop_text)

            # السعر والكمية
            price_txt = ""
            if tpl.price:
                price_txt = f"{tpl.price} د.ج"
            elif req.price:
                price_txt = f"{req.price} د.ج"

            mult_txt = ""
            if tpl.multiplier:
                mult_txt = tpl.multiplier
            elif req.quantity:
                mult_txt = req.quantity

            if price_txt or mult_txt:
                display = price_txt
                if mult_txt:
                    display += f"  ×{mult_txt}"
                try:
                    c.setFont(fs.priceFont or "Helvetica-Bold", fs.priceSize)
                except:
                    c.setFont("Helvetica-Bold", fs.priceSize)
                c.drawCentredString(x + label_w_pt / 2, y + 18, display)

        # رسم الملصقات بالترتيب (صف-عمود)
        count = 0
        for r in range(rows):
            for col in range(cols):
                if count >= to_generate:
                    break
                x = margin + col * label_w_pt
                y = page_h_pt - margin - label_h_pt - r * label_h_pt
                draw_label(x, y, desired[count])
                count += 1
            if count >= to_generate:
                break

        c.save()
        return FileResponse(OUT_PDF, media_type="application/pdf", filename="labels.pdf")

    except HTTPException as he:
        raise he
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})