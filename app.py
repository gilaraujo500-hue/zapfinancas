from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta
import openai
import os
from flask_sqlalchemy import SQLAlchemy
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

openai.api_key = os.environ.get('OPENAI_API_KEY')

# Credenciais do Whapi (adiciona no Railway)
WHAPI_TOKEN = os.environ.get('WHAPI_TOKEN')  # Teu token do Whapi (UEN7YQBKZ2HBVIMY93G5X)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(30), unique=True)
    trial_end = db.Column(db.DateTime)
    paid = db.Column(db.Boolean, default=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    value = db.Column(db.Float)
    description = db.Column(db.String(200))
    category = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    data = request.get_json()
    phone = data.get('chatId', '') or data.get('phone', '')  # Whapi usa chatId ou phone
    text = data.get('text', '') or data.get('message', {}).get('text', '').lower()

    if not phone or not text:
        return jsonify({}), 200

    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, trial_end=datetime.utcnow() + timedelta(days=3))
        db.session.add(user)
        db.session.commit()
        send_message(phone, "Bem-vindo! Você tem 3 dias grátis. Mande um gasto para registrar.")
        return jsonify({}), 200

    if datetime.utcnow() > user.trial_end and not user.paid:
        send_message(phone, "Seu trial de 3 dias acabou. Valor: R$ 19,90/mês")
        return jsonify({}), 200

    result = process_text(text)
    if result:
        trans = Transaction(user_id=user.id, value=result['value'], description=result['desc'], category=result['cat'])
        db.session.add(trans)
        db.session.commit()
        total = db.session.query(db.func.sum(Transaction.value)).filter_by(user_id=user.id).scalar() or 0
        reply = f"""✅ Registrado!

💰 R$ {result['value']:.2f}
📝 {result['desc'].title()}
🏷️ {result['cat']}
📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}

Total do mês: R$ {total:.2f}"""
    else:
        reply = "Não entendi. Tente: 'Gastei 120 no mercado'"

    send_message(phone, reply)
    return jsonify({}), 200

def process_text(text):
    prompt = f"""Extraia APENAS em JSON válido: valor, descrição e categoria (Alimentação/Transporte/Lazer/Saúde/Moradia/Outros) do texto: "{text}"
Formato: {{"value": 0.0, "desc": "string", "cat": "string"}}
Se não for gasto, retorne null."""
    try:
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role": "system", "content": prompt}], temperature=0)
        json_str = resp.choices[0].message.content.strip()
        if json_str == "null":
            return None
        data = json.loads(json_str)
        data['value'] = float(data['value'])
        return data
    except:
        return None

def send_message(phone, message):
    url = f"https://gate.whapi.cloud/sendMessage?token={WHAPI_TOKEN}"
    payload = {
        "chatId": phone.replace("+", "").replace("whatsapp:", ""),
        "text": message
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass  # Não trava se falhar

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
