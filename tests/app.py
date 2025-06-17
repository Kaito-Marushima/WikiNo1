from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    """トップページ"""
    return "Hello, Wiki!"

# ↓このif文はインデントしない（行頭から書く）
if __name__ == '__main__':
#   ↓この行は必ずインデントする（半角スペース4つ）
    app.run(debug=True)