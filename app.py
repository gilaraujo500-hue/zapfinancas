@app.route('/whatsapp', methods=['POST'])
def whatsapp():
    data = request.get_json()

    # Extrai número e texto do formato do Whapi
    try:
        phone = data['chats_updates'][0]['after_update']['id'].split('@')[0]
        text = data['chats_updates'][0]['after_update']['last_message']['text']['body'].lower()
    except:
        return jsonify({}), 200

    # Resto do código exatamente como antes
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
