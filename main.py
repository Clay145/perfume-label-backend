from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
import os

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

@app.get("/generate_label")
def generate_label(perfume_name: str, shop_name: str, price: str = "", multiplier: str = "", copies: int = 1):
    try:
        file_path = "labels.pdf"
        c = canvas.Canvas(file_path, pagesize=A4)

        width, height = A4
        label_size = 113.39  # 4 سم
        margin = 10

        cols = int((width - margin) // label_size)
        rows = int((height - margin) // label_size)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "logo.png")

        logo = None
        if os.path.exists(logo_path):
            try:
                logo = ImageReader(logo_path)
            except Exception as e:
                print("⚠️ خطأ في تحميل اللوجو:", e)
        else:
            print("⚠️ لم يتم العثور على logo.png")

        def draw_label(x, y):
            # ✅ الإطار الأساسي
            c.setLineWidth(1)
            c.setStrokeColor(colors.black)
            c.roundRect(x + 3, y + 3, label_size - 6, label_size - 6, 8, stroke=1, fill=0)


            # ✅ اللوجو في الأعلى
            if logo:
                c.drawImage(logo, x + (label_size - 30) / 2, y + label_size - 40, 30, 30, mask="auto")

            # ✅ اسم العطر (بخط أكبر)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(x + label_size / 2, y + label_size / 2 + 18, perfume_name)

            # ✅ اسم المحل
            c.setFont("Helvetica", 8)
            c.drawCentredString(x + label_size / 2, y + label_size / 2, shop_name)

            # ✅ السعر والضرب يظهران بوضوح أسفل الاسم
            if price or multiplier:
                c.setFont("Helvetica-Bold", 9)
                display_text = ""
                if price:
                    display_text += f" Prix: {price} "
                if multiplier:
                    display_text += f"  (×{multiplier})"
                c.drawCentredString(x + label_size / 2, y + 20, display_text.strip())

        # ✅ رسم عدد الملصقات المطلوب
        count = 0
        for row in range(rows):
            for col in range(cols):
                if count >= copies:
                    break
                x = margin + col * label_size
                y = height - margin - label_size - row * label_size
                draw_label(x, y)
                count += 1
            if count >= copies:
                break

        c.save()
        print(f"✅ PDF جاهز بعدد {copies} ملصقات (السعر والضرب مضافان)")
        return FileResponse(file_path, media_type="application/pdf", filename="labels.pdf")

    except Exception as e:
        print("❌ خطأ أثناء إنشاء الملف:", e)
        return {"error": str(e)}