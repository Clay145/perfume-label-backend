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

# ===== CORS =====
origins = [
    "http://localhost:5173",
    "https://perfume-label-frontend.vercel.app",
    # أضف هنا رابط الواجهة المنشورة إن لزم
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== helpers =====
MM_TO_PT = 2.83465  # 1 mm ≈ 2.83465 points

def mm_to_pt(mm: float) -> float:
    return float(mm) * MM_TO_PT

# register arabic font if provided
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AMIRI_PATH = os.path.join(BASE_DIR, "Amiri-Regular.ttf")
if os.path.exists(AMIRI_PATH):
    try:
        pdfmetrics.registerFont(TTFont("Amiri", AMIRI_PATH))
        ARABIC_FONT_AVAILABLE = True
    except Exception as e:
        print("Could not register Amiri:", e)
        ARABIC_FONT_AVAILABLE = False
else:
    ARABIC_FONT_AVAILABLE = False

# ===== API for upload logo =====
@app.post("/upload_logo")
async def upload_logo(file: UploadFile = File(...)):
    try:
        logo_path = os.path.join(BASE_DIR, "logo.png")
        with open(logo_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return {"message": "Logo uploaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== Data models =====
class TemplateItem(BaseModel):
    perfume_name: str
    price: Optional[str] = ""
    multiplier: Optional[str] = ""
    shop_name: Optional[str] = None  # if None, use settings.shop_name
    # validation helpers
    @validator("price")
    def price_digits(cls, v):
        if v is None or v == "":
            return v
        # allow numbers only (optionally with spaces or commas)
        cleaned = v.replace(" ", "").replace(",", "")
        if not cleaned.isdigit():
            raise ValueError("price must contain digits only")
        return v

    @validator("multiplier")
    def multiplier_digits(cls, v):
        if v is None or v == "":
            return v
        cleaned = v.replace(" ", "").replace("×", "").replace("x", "")
        if not cleaned.isdigit():
            raise ValueError("multiplier must contain digits only")
        return v

class LabelSettings(BaseModel):
    shop_name: str
    copies: int = Field(1, ge=1, le=35)
    label_width_mm: float = Field(40.0, gt=0)   # mm
    label_height_mm: float = Field(40.0, gt=0)  # mm
    radius_mm: float = Field(2.0, ge=0)  # corner radius in mm
    font_perfume_name: str = "Helvetica-Bold"
    font_shop_name: str = "Times-Italic"
    font_perfume_size: int = 12
    font_shop_size: int = 10
    font_price_size: int = 9
    templates: Optional[List[TemplateItem]] = None

    @validator("label_width_mm")
    def width_within_page(cls, v):
        # ensure at least one column fits in A4 width with margin
        page_w_pt, page_h_pt = A4
        max_width_mm = page_w_pt / MM_TO_PT
        if v > max_width_mm:
            raise ValueError(f"label width too large for A4 (max {max_width_mm:.1f} mm)")
        return v

    @validator("label_height_mm")
    def height_within_page(cls, v):
        page_w_pt, page_h_pt = A4
        max_height_mm = page_h_pt / MM_TO_PT
        if v > max_height_mm:
            raise ValueError(f"label height too large for A4 (max {max_height_mm:.1f} mm)")
        return v

# ===== PDF generation =====
@app.post("/generate_label")
def generate_label(settings: LabelSettings):
    try:
        # compute label sizes in points
        label_w_pt = mm_to_pt(settings.label_width_mm)
        label_h_pt = mm_to_pt(settings.label_height_mm)
        radius_pt = mm_to_pt(settings.radius_mm)

        page_w_pt, page_h_pt = A4
        margin = 10  # points

        # check how many columns/rows fit
        cols = max(1, int((page_w_pt - margin) // label_w_pt))
        rows = max(1, int((page_h_pt - margin) // label_h_pt))
        max_labels = cols * rows
        # debug
        # print("cols,rows,max_labels", cols, rows, max_labels)

        # prepare templates list:
        templates = settings.templates or []
        if not templates:
            raise HTTPException(status_code=400, detail="No templates provided")

        # flatten the desired labels list:
        labels_list = []
        # if templates length >= copies, use first copies templates
        # else repeat templates cyclically until copies reached
        idx = 0
        while len(labels_list) < settings.copies:
            item = templates[idx % len(templates)]
            labels_list.append(item)
            idx += 1

        # enforce max_labels
        to_generate = min(len(labels_list), max_labels)

        # prepare logo if exists
        logo_path = os.path.join(BASE_DIR, "logo.png")
        logo = ImageReader(logo_path) if os.path.exists(logo_path) else None

        # create canvas
        out_path = os.path.join(BASE_DIR, "labels.pdf")
        c = canvas.Canvas(out_path, pagesize=A4)

        # choose fonts fallback: if Arabic font available, register mapping as "Amiri"
        arabic_font = "Amiri" if ARABIC_FONT_AVAILABLE else None

        def draw_one(x, y, tpl: TemplateItem):
            # outer rounded rect
            c.setLineWidth(0.8)
            c.setStrokeColor(colors.black)
            # use radius_pt; reportlab expects radius as float
            c.roundRect(x + 3, y + 3, label_w_pt - 6, label_h_pt - 6, radius_pt, stroke=1, fill=0)

            # logo centered top
            if logo:
                # calculate logo size to fit (proportional) - optional
                # here we place it using fraction of label height
                logo_w = min(label_w_pt * 0.5, label_w_pt * 0.3)
                logo_h = logo_w
                c.drawImage(logo, x + (label_w_pt - logo_w) / 2, y + label_h_pt - logo_h - 8, logo_w, logo_h, mask='auto')

            # perfume name
            # choose font name (if user provided an arabic font choice, you could map)
            font_perf_name = settings.font_perfume_name
            try:
                c.setFont(font_perf_name, settings.font_perfume_size)
            except:
                if arabic_font and contains_arabic(tpl.perfume_name):
                    c.setFont(arabic_font, settings.font_perfume_size)
                else:
                    c.setFont("Helvetica-Bold", settings.font_perfume_size)

            c.drawCentredString(x + label_w_pt / 2, y + label_h_pt / 2 + settings.font_perfume_size/2 + 6, tpl.perfume_name)

            # shop name (use template shop_name if given else settings.shop_name)
            shop_text = tpl.shop_name if (tpl.shop_name and tpl.shop_name.strip()) else settings.shop_name
            try:
                c.setFont(settings.font_shop_name, settings.font_shop_size)
            except:
                if arabic_font and contains_arabic(shop_text):
                    c.setFont(arabic_font, settings.font_shop_size)
                else:
                    c.setFont("Times-Italic", settings.font_shop_size)

            c.drawCentredString(x + label_w_pt / 2, y + label_h_pt / 2 - settings.font_shop_size/2 - 2, shop_text)

            # price and multiplier (ensure numeric)
            if tpl.price or tpl.multiplier:
                price_txt = ""
                if tpl.price:
                    # sanitize digits
                    cleaned = tpl.price.replace(" ", "").replace(",", "")
                    price_txt += f"{cleaned} د.ج"
                if tpl.multiplier:
                    cleaned_m = tpl.multiplier.replace(" ", "").replace("×", "").replace("x", "")
                    price_txt += f" (×{cleaned_m})"
                c.setFont("Helvetica-Bold", settings.font_price_size)
                c.drawCentredString(x + label_w_pt / 2, y + 18, price_txt)

            # extra fields bottom
            if tpl and hasattr(tpl, "extra_fields") and tpl.extra_fields:
                c.setFont("Helvetica", 7)
                y_off = 10
                for f in tpl.extra_fields:
                    txt = f"{f.get('label','')}: {f.get('value','')}"
                    c.drawCentredString(x + label_w_pt / 2, y + y_off, txt)
                    y_off += 9

        # helper to detect Arabic (very simple)
        def contains_arabic(s: str) -> bool:
            for ch in s:
                if "\u0600" <= ch <= "\u06FF" or "\u0750" <= ch <= "\u077F":
                    return True
            return False

        # draw labels row-major
        count = 0
        for r in range(rows):
            for cidx in range(cols):
                if count >= to_generate:
                    break
                x = margin + cidx * label_w_pt
                y = page_h_pt - margin - label_h_pt - r * label_h_pt
                draw_one(x, y, labels_list[count])
                count += 1
            if count >= to_generate:
                break

        c.save()
        return FileResponse(out_path, media_type="application/pdf", filename="labels.pdf")
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})