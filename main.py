# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
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

# ===== نماذج البيانات (Models) =====

class TemplateItem(BaseModel):
    perfumeName: Optional[str] = ""
    price: Optional[str] = ""
    multiplier: Optional[str] = ""
    shopName: Optional[str] = ""
    extraInfo: Optional[str] = ""

    @field_validator("price")
    @classmethod
    def price_must_be_digits(cls, v):
        if not v:
            return v
        cleaned = v.replace(" ", "").replace(",", "")
        if not cleaned.isdigit():
            raise ValueError("price must contain digits only")
        return v

    @field_validator("multiplier")
    @classmethod
    def multiplier_must_be_digits(cls, v):
        if not v:
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

class StyleSettings(BaseModel):
    theme: Optional[str] = "gold_black"
    primaryColor: Optional[str] = "#D4AF37"  # hex string
    accentColor: Optional[str] = "#080808"
    borderColor: Optional[str] = None

class GenerateRequest(BaseModel):
    shopName: Optional[str] = ""
    copies: int = Field(1, ge=1, le=35)
    labelWidth: float
    labelHeight: float
    borderRadius: float
    fontSettings: FontSettings
    templates: List[TemplateItem]
    price: str | None = None
    quantity: str | None = None
    perfumeName: str | None = None
    style: Optional[StyleSettings] = StyleSettings()
    phone: Optional[str] = None

    @field_validator("borderRadius", mode="before")
    @classmethod
    def parse_radius(cls, v):
        # يحول أي قيمة نصية إلى float تلقائيًا
        try:
            return float(v)
        except:
            raise ValueError("borderRadius must be a number")

    @field_validator("labelWidth")
    @classmethod
    def width_fits_a4(cls, v):
        from reportlab.lib.pagesizes import A4
        page_w_mm = A4[0] / MM_TO_PT
        if v > page_w_mm:
            raise ValueError(f"label width must be <= page width ({page_w_mm:.1f} mm)")
        return v

    @field_validator("labelHeight")
    @classmethod
    def height_fits_a4(cls, v):
        from reportlab.lib.pagesizes import A4
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

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import status
from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print("❌ Validation error in request:")
    print(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())},
    )

# --- Start replacement generate_label (paste into main.py, استبدل الدالة الموجودة) ---
@app.post("/generate_label")
def generate_label(req: GenerateRequest):
    try:
        # تحقق من وجود قوالب
        if not req.templates or len(req.templates) == 0:
            raise HTTPException(status_code=400, detail="templates list is required and must contain at least one item")

        # تحويل الوحدات (MM -> points)
        label_w_pt = mm_to_pt(req.labelWidth)
        label_h_pt = mm_to_pt(req.labelHeight)
        radius_pt = mm_to_pt(req.borderRadius)

        page_w_pt, page_h_pt = A4
        margin = mm_to_pt(6)  # هامش ثابت صغير بالـ points

        # حساب الأعمدة/الصفوف الممكنة على صفحة A4
        cols = max(1, int((page_w_pt - margin) // label_w_pt))
        rows = max(1, int((page_h_pt - margin) // label_h_pt))
        max_labels_per_page = cols * rows

        # بناء قائمة الملصقات المطلوبة (نكرر القوالب حتى نصل للـ copies)
        desired = []
        idx = 0
        while len(desired) < req.copies:
            tpl = req.templates[idx % len(req.templates)]
            desired.append(tpl)
            idx += 1

        to_generate = min(len(desired), max_labels_per_page)

        # اقرأ الألوان من req.style
        # ✅ اقرأ ألوان المستخدم من الـ frontend (أو استخدم القيم الافتراضية)
        primary_hex = (req.style.primaryColor or "#D4AF37").lstrip("#")  # النصوص / الإطار
        accent_hex = (req.style.accentColor or "#080808").lstrip("#")    # الخلفية
        # ✅ حولها إلى RGB في نطاق 0..1
        primary_rgb = tuple(int(primary_hex[i:i+2], 16) / 255 for i in (0, 2, 4))
        accent_rgb = tuple(int(accent_hex[i:i+2], 16) / 255 for i in (0, 2, 4))

        border_hex = (req.style.borderColor or req.style.primaryColor or "#D4AF37").lstrip("#")
        border_rgb = tuple(int(border_hex[i:i+2], 16)/255 for i in (0,2,4))


        # تحويل hex إلى أرقام RGB 0..1
        r = int(primary_hex[0:2], 16)/255
        g = int(primary_hex[2:4], 16)/255
        b = int(primary_hex[4:6], 16)/255
        # ثم استخدم c.setFillColorRGB(r,g,b) عند رسم النص بدل القيم الثابتة للذهب

        # تسجيل خطوط فخمة إن وُجدت (ضع ملفات TTF في مجلد fonts/)
        def try_register(name, path):
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    return name
                except Exception as e:
                    print("⚠️ font register failed:", path, e)
            return None

        # أمثلة خطوط (ضع الملفات في مجلد fonts/)
        fonts_dir = os.path.join(BASE_DIR, "fonts")
        PLAYFAIR = try_register("Playfair", os.path.join(fonts_dir, "PlayfairDisplay-Bold.ttf"))  # إن أردت
        CINZEL = try_register("Cinzel", os.path.join(fonts_dir, "CinzelDecorative-Regular.ttf"))
        if os.path.exists(AMIRI_TTF):
            try:
                pdfmetrics.registerFont(TTFont("Amiri", AMIRI_TTF))
                # ARABIC_FONT already set earlier
            except Exception as e:
                print("⚠️ Amiri register failed:", e)

        # ألوان افتراضية (يمكن استقبالها من payload لاحقًا)
        GOLD = primary_rgb     # اللون الأساسي (للنصوص والإطار)
        DARK = accent_rgb      # لون الخلفية


        # تحميل اللوجو إن وُجد
        logo = ImageReader(LOGO_PATH) if os.path.exists(LOGO_PATH) else None

        # أنشئ الـ canvas
        c = canvas.Canvas(OUT_PDF, pagesize=A4)

        # دالة مساعدة لاكتشاف العربية
        def contains_arabic(s: str) -> bool:
            if not s:
                return False
            for ch in s:
                if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F":
                    return True
            return False

        # دالة رسم الملصق الفاخر
        def draw_label(x, y, tpl):
            # صندوق داخلي ملون (خلفية داكنة داخل الإطار)
            padding = 8  # نقاط
            inner_x = x + 3
            inner_y = y + 3
            inner_w = label_w_pt - 6
            inner_h = label_h_pt - 6

            # خلفية داكنة
            # خلفية قابلة للتخصيص
            c.setFillColorRGB(*DARK)
            c.roundRect(inner_x, inner_y, inner_w, inner_h, radius_pt, stroke=0, fill=1)

            # إطار باللون الذي اختاره المستخدم
            c.setLineWidth(1.2)
            c.setStrokeColorRGB(*GOLD)
            c.roundRect(inner_x + 1, inner_y + 1, inner_w - 2, inner_h - 2, radius_pt, stroke=1, fill=0)

            # منطقة اللوجو العلوية (مركزي)
            logo_area_h = inner_h * 0.22
            if logo:
                # ضع اللوجو بحجم نسبي داخل الدائرة
                max_logo_w = inner_w * 0.4
                max_logo_h = logo_area_h - 6
                logo_w = min(max_logo_w, max_logo_h)
                logo_h = logo_w
                lx = inner_x + (inner_w - logo_w) / 2
                ly = inner_y + inner_h - logo_h - padding - 2
                try:
                    c.drawImage(logo, lx, ly, logo_w, logo_h, mask='auto')
                except Exception as e:
                    print("⚠️ drawImage failed:", e)

            # إعداد الخطوط (اختر الأولية من fontSettings أو تعليق بديل)
            fs = req.fontSettings or FontSettings()

            # اسم العطر — بمساحة كبيرة ومركزية
            pname = tpl.perfumeName or ""
            name_font = None
            if contains_arabic(pname) and "Amiri" in pdfmetrics.getRegisteredFontNames():
                name_font = "Amiri"
            elif PLAYFAIR:
                name_font = PLAYFAIR
            elif CINZEL:
                name_font = CINZEL
            else:
                name_font = fs.perfumeFont or "Helvetica-Bold"

            name_size = fs.perfumeSize if getattr(fs, "perfumeSize", None) else max(12, int(min(inner_w, inner_h) * 0.12))
            try:
                c.setFont(name_font, name_size)
            except Exception:
                c.setFont("Helvetica-Bold", name_size)

            c.setFillColorRGB(*GOLD)
            # احسب موضع الاسم مع مراعاة المساحة العلوية
            name_y = inner_y + inner_h * 0.56
            c.drawCentredString(inner_x + inner_w / 2, name_y, pname)

            # خط زخرفي ذهبي صغير (فاصل) تحت الاسم
            deco_y = name_y - (name_size * 0.8)
            c.setLineWidth(1)
            c.setStrokeColorRGB(*GOLD)
            line_w = inner_w * 0.4
            c.line(inner_x + (inner_w - line_w) / 2, deco_y, inner_x + (inner_w + line_w) / 2, deco_y)

            # اسم المحل تحت الفاصل (أصغر حجماً)
            shop_text = tpl.shopName or req.shopName or ""
            shop_font = "Amiri" if contains_arabic(shop_text) and "Amiri" in pdfmetrics.getRegisteredFontNames() else (fs.shopFont or "Times-Italic")
            try:
                c.setFont(shop_font, fs.shopSize)
            except Exception:
                c.setFont("Times-Italic", fs.shopSize)
            c.setFillColorRGB(0.86, 0.84, 0.8)  # لون بيج فاتح لخفض حدة الذهبية هنا قليلاً
            c.drawCentredString(inner_x + inner_w / 2, deco_y - (fs.shopSize * 1.2), shop_text)

            # خط زخرفي ذهبي صغير (فاصل) تحت اسم المحل
            deco_y = name_y - (name_size * 0.8)
            c.setLineWidth(1)
            c.setStrokeColorRGB(*GOLD)
            line_w = inner_w * 0.4
            c.line(inner_x + (inner_w - line_w) / 2, deco_y, inner_x + (inner_w + line_w) / 2, deco_y)

            # أسفل: السعر، الكمية، رقم الهاتف (محاذاة مركزية أو صفّية)
            price_txt = tpl.price or req.price or ""
            mult_txt = tpl.multiplier or "" or req.quantity or ""
            bottom_y = inner_y + padding + 8

            # نص السعر (ذو وزن متوسط)
            if price_txt:
                price_display = f"Prix(DA):{price_txt} "
                try:
                    c.setFont(fs.priceFont or "Helvetica-Bold", fs.priceSize)
                except:
                    c.setFont("Helvetica-Bold", fs.priceSize)
                c.setFillColorRGB(*GOLD)
                c.drawCentredString(inner_x + inner_w / 2, bottom_y + (fs.priceSize * 0.6), price_display)

            # الكمية بجانب السعر (إذا وُجدت)
            if mult_txt:
                qty_display = f"(×{mult_txt})"
                try:
                    c.setFont(fs.quantityFont or "Helvetica", fs.quantitySize)
                except:
                    c.setFont("Helvetica", fs.quantitySize)
                c.setFillColorRGB(0.86, 0.84, 0.8)
                # نضعها على يمين السعر قليلاً
                c.drawString(inner_x + inner_w/2 + 30, bottom_y + (fs.priceSize * 0.6), qty_display)

            # إذا وُجدت إضافات، اطبعها تحت اسم المحل بخط صغير
            extra = tpl.extraInfo or ""
            if extra:
                extra_font = "Amiri" if contains_arabic(extra) and "Amiri" in pdfmetrics.getRegisteredFontNames() else (fs.shopFont or "Times-Italic")
                extra_size = max(7, int(fs.shopSize * 0.85))
                try:
                    c.setFont(extra_font, extra_size)
                except Exception:
                    c.setFont("Times-Italic", extra_size)
                c.setFillColorRGB(0.86, 0.84, 0.8)
                c.drawCentredString(inner_x + inner_w / 2, deco_y - (fs.shopSize * 1.2) - (extra_size * 1.1), extra)


            # رقم الهاتف (إذا وُجد في extra field أو shopName—يمكن إضافة حقل لاحقاً)
            # إذا أردت استخدام حقل إضافي، أضفه ك tpl.extra.phone أو req.extra_phone
            # مثال: عرض نص صغير أسفل الجانب الأيمن
            phone = None
            # try extra fields
            if isinstance(tpl, dict):
                phone = tpl.get("phone") or tpl.get("tel")
            else:
                # TemplateItem يمكن توسيعه لاحقًا
                phone = getattr(tpl, "phone", None)
            if not phone:
                # حاول جلب من req (إذا أضفنا حقل لاحقًا)
                phone = getattr(req, "phone", None)

            if phone:
                try:
                    c.setFont(fs.quantityFont or "Helvetica", max(7, fs.quantitySize - 1))
                except:
                    c.setFont("Helvetica", max(7, fs.quantitySize - 1))
                c.setFillColorRGB(0.8, 0.78, 0.7)
                c.drawRightString(inner_x + inner_w - padding - 2, inner_y + 6, phone)

        # رسم الملصقات صفياً وعمودياً
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
        # طباعة الخطأ على الطرفية لتسهيل التصحيح
        print("❌ generate_label error:", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
# --- End replacement generate_label ---