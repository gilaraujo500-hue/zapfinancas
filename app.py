from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import openai
import os
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/postgres').replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

openai.api_key = os.environ.get('OPENAI_API_KEY')

# --- Banco de dados simples ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True)
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

# --- Rota principal (webhook) ---
@app.route('/whatsapp', methods=['POST'])
def webhook():
    data = request.get_json()
    
    # Z-API manda assim
    phone = data.get('phone', '')
    message = data.get('message', {}).get('text', '').lower()

    if not phone or not message:
        return jsonify({}), 200

    # Procura ou cria usuário
    user = User.query.filter_by(phone=phone).first()
    if not user:
        user = User(phone=phone, trial_end=datetime.utcnow() + timedelta(days=3))
        db.session.add(user)
        db.session.commit()
        return jsonify({"phone": phone, "message": "Bem-vindo! Você tem 3 dias grátis. Mande um gasto para registrar."})

    # Bloqueia após trial
    if datetime.utcnow() > user.trial_end and not user.paid:
        return jsonify({"phone": phone, "message": "Seu trial de 3 dias acabou. Valor: R$ 19,90/mês"})

    # Processa o gasto
    result = process_message(message)
    if result:
        trans = Transaction(user_id=user.id, value=result['value'], description=result['desc'], category=result['cat'])
        db.session.add(trans)
        db.session.commit()
        
        total = db.session.query(db.func.sum(Transaction.value)).filter(Transaction.user_id == user.id).scalar() or 0
        
        reply = f"""✅ Registrado!

💰 R$ {result['value']:.2f}
📝 {result['desc'].title()}
🏷️ {result['cat']}
📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}

💡 Total do mês: R$ {total:.2f}"""
    else:
        reply = "Não entendi. Tente: Gastei 120 no mercado"

    return jsonify({"phone": phone, "message": reply})

# --- Processa a mensagem com GPT ---
def process_message(text):
    prompt = f"""Extraia APENAS valor e descrição em JSON:
Texto: "{text}"
Retorne:
{{"value": 0.0, "desc": "string", "cat": "Alimentação/Transporte/Lazer/Saúde/Moradia/Outros"}}
Se não for gasto, retorne null."""
    try:
        resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role": "system", "content": prompt}], temperature=0)
        json_str = resp.choices[0].message.content.strip()
        if json_str == "null":
            return None
        data = eval(json_str)
        return {"value": float(data['value']), "desc": data['desc'], "cat": data['cat']}
    except:
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
