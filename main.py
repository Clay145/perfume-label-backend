from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
import os
import shutil

app = FastAPI()

origins = [
    "http://localhost:5173",
    "https://perfume-label-frontend.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ تحميل خط عربي جميل (Amiri أو Cairo)
base_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(base_dir, "Amiri-Regular.ttf")
if os.path.exists(font_path):
    pdfmetrics.registerFont(TTFont("ArabicFont", font_path))
else:
    print("⚠️ لم يتم العثور على الخط Amiri-Regular.ttf - سيتم استخدام Helvetica")

# ✅ رفع اللوجو وتغييره
@app.post("/upload_logo")
async def upload_logo(file: UploadFile = File(...)):
    try:
        logo_path = os.path.join(base_dir, "logo.png")
        with open(logo_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"message": "✅ تم تحديث اللوجو بنجاح"}
    except Exception as e:
        return {"error": str(e)}


# ✅ نموذج إعدادات الملصق
class LabelSettings(BaseModel):
    perfume_name: str
    shop_name: str
    price: str | None = ""
    multiplier: str | None = ""
    copies: int = 1
    label_width: float = 113.39
    label_height: float = 113.39
    font_perfume: int = 12
    font_shop: int = 10
    font_price: int = 9
    logo_size: int = 30
    logo_y_offset: int = 40
    extra_fields: list[dict] | None = None
    language: str = "ar"  # ar أو en


@app.post("/generate_label")
def generate_label(settings: LabelSettings):
    try:
        file_path = "labels.pdf"
        c = canvas.Canvas(file_path, pagesize=A4)
        page_width, page_height = A4
        margin = 10

        # تحميل اللوجو إن وجد
        logo_path = os.path.join(base_dir, "logo.png")
        logo = ImageReader(logo_path) if os.path.exists(logo_path) else None

        # عدد الصفوف والأعمدة
        cols = int((page_width - margin) // settings.label_width)
        rows = int((page_height - margin) // settings.label_height)

        # اختيار الخط
        if settings.language == "ar" and os.path.exists(font_path):
            main_font = "ArabicFont"
        else:
            main_font = "Helvetica-Bold"

        def draw_label(x, y):
            # الإطار
            c.setLineWidth(1)
            c.setStrokeColor(colors.black)
            c.roundRect(
                x + 3, y + 3,
                settings.label_width - 6,
                settings.label_height - 6,
                8, stroke=1, fill=0
            )

            # اللوجو
            if logo:
                c.drawImage(
                    logo,
                    x + (settings.label_width - settings.logo_size) / 2,
                    y + settings.label_height - settings.logo_y_offset,
                    settings.logo_size,
                    settings.logo_size,
                    mask="auto"
                )

            # اسم العطر
            c.setFont(main_font, settings.font_perfume)
            c.drawCentredString(x + settings.label_width / 2, y + settings.label_height / 2 + 10, settings.perfume_name)

            # اسم المحل
            c.setFont(main_font, settings.font_shop)
            c.drawCentredString(x + settings.label_width / 2, y + settings.label_height / 2 - 5, settings.shop_name)

            # السعر والضرب
            if settings.price or settings.multiplier:
                c.setFont(main_font, settings.font_price)
                text = ""
                if settings.price:
                    text += f"السعر: {settings.price} DA "
                if settings.multiplier:
                    text += f"(×{settings.multiplier})"
                c.drawCentredString(x + settings.label_width / 2, y + 20, text.strip())

            # الحقول الإضافية
            if settings.extra_fields:
                c.setFont(main_font, 8)
                y_offset = 10
                for field in settings.extra_fields:
                    label_text = f"{field['label']}: {field['value']}"
                    c.drawCentredString(x + settings.label_width / 2, y + y_offset, label_text)
                    y_offset -= 10

        # رسم كل الملصقات
        count = 0
        for row in range(rows):
            for col in range(cols):
                if count >= settings.copies:
                    break
                x = margin + col * settings.label_width
                y = page_height - margin - settings.label_height - row * settings.label_height
                draw_label(x, y)
                count += 1
            if count >= settings.copies:
                break

        c.save()
        return FileResponse(file_path, media_type="application/pdf", filename="labels.pdf")

    except Exception as e:
        print("❌ خطأ:", e)
        return JSONResponse(content={"error": str(e)})