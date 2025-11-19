import requests
import json

url = "http://127.0.0.1:8000/generate_label"

payload = {
  "shopName": "Test Shop",
  "copies": 1,
  "labelWidth": 50,
  "labelHeight": 50,
  "borderRadius": 2,
  "fontSettings": {
    "perfumeFont": "Helvetica-Bold",
    "perfumeSize": 12,
    "shopFont": "Times-Italic",
    "shopSize": 10,
    "priceFont": "Helvetica-Bold",
    "priceSize": 9,
    "quantityFont": "Helvetica",
    "quantitySize": 9,
    "extraInfoSize": 9
  },
  "templates": [
    {
      "perfumeName": "Test Perfume",
      "price": "1000",
      "multiplier": "1",
      "shopName": "Shop",
      "extraInfo": "Extra Info"
    }
  ],
  "style": {
    "theme": "gold_black",
    "primaryColor": "#D4AF37",
    "accentColor": "#080808",
    "extraInfoColor": "#E5E0D1",
    "borderColor": "#D4AF37"
  }
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.text)
except Exception as e:
    print(f"Request failed: {e}")
