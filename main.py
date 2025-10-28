from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
import os

app = FastAPI()

# ✅ هنا ضع نطاقاتك المسموح بها فقط
origins = [
    "http://localhost:5173",  # للتجريب محليًا
    "https://perfume-label-frontend.vercel.app"  # موقعك المنشور
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # لا تتركها "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/generate_label")
def generate_label(perfume_name: str, shop_name: str):
    try:
        file_path = "labels.pdf"
        c = canvas.Canvas(file_path, pagesize=A4)

        width, height = A4
        label_size = 113.39  # 4 سم
        margin = 10

        cols = int((width - margin) // label_size)
        rows = int((height - margin) // label_size)

        x_start = margin
        y_start = height - margin - label_size

        # ✅ تحميل اللوجو
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

        # ✅ دالة لرسم مستطيل بزوايا دائرية
        def draw_rounded_rect(x, y, w, h, r, color=colors.black):
            c.setLineWidth(1)
            c.setStrokeColor(color)
            c.roundRect(x, y, w, h, r, stroke=1, fill=0)

        # ✅ دالة لرسم الإطار الخارجي للفصل بين الملصقات
        def draw_outer_border(x, y, w, h, color=colors.lightgrey):
            c.setLineWidth(0.5)
            c.setStrokeColor(color)
            c.rect(x - 2, y - 2, w + 4, h + 4)  # إطار أوسع قليلاً من الداخلي

        # ✅ رسم كل الملصقات
        for row in range(rows):
            for col in range(cols):
                x = x_start + col * label_size
                y = y_start - row * label_size

                # الإطار الخارجي للفصل بين الملصقات
                draw_outer_border(x, y, label_size, label_size)

                # الإطار الداخلي بزوايا دائرية
                draw_rounded_rect(x + 3, y + 3, label_size - 6, label_size - 6, r=8, color=colors.black)

                # اللوجو
                if logo:
                    logo_w, logo_h = 30, 30
                    c.drawImage(
                        logo,
                        x + (label_size - logo_w) / 2,
                        y + label_size - logo_h - 8,
                        logo_w,
                        logo_h,
                        mask="auto"
                    )

                # النص
                c.setFont("Helvetica-Bold", 10)
                c.drawCentredString(x + label_size / 2, y + label_size / 2 + 10, perfume_name)
                c.setFont("Helvetica", 8)
                c.drawCentredString(x + label_size / 2, y + label_size / 2 - 10, shop_name)

        c.save()
        print("✅ PDF تم إنشاؤه بنجاح")
        return FileResponse(file_path, media_type="application/pdf", filename="labels.pdf")

    except Exception as e:
        print("❌ خطأ أثناء إنشاء الملف:", e)
        return {"error": str(e)}