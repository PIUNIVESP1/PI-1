import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'univesp-logistica-2026-final'

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'precos.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    listas = db.relationship('Lista', backref='dono', lazy=True)

class Preco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto = db.Column(db.String(100), nullable=False)
    mercado = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    is_promo = db.Column(db.Boolean, default=False) # CAMPO NOVO
    data = db.Column(db.DateTime, default=datetime.utcnow)

class Lista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    itens = db.relationship('ItemLista', backref='lista', cascade="all, delete-orphan", lazy=True)

class ItemLista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_nome = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=1)
    marcado = db.Column(db.Boolean, default=False)
    lista_id = db.Column(db.Integer, db.ForeignKey('lista.id'), nullable=False)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS DE LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('listas'))
        flash('Login inválido!')
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        u = request.form.get('username').strip()
        p = request.form.get('password')
        if User.query.filter_by(username=u).first(): flash('Usuário já existe!')
        else:
            novo = User(username=u, password=generate_password_hash(p))
            db.session.add(novo); db.session.commit()
            return redirect(url_for('login'))
    return render_template('cadastro.html')

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('login'))

# --- LISTAS ---
@app.route('/')
@app.route('/listas')
@login_required
def listas():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    
    # Lógica para Alerta de Promoção: busca promoções das últimas 24 horas
    limite_promo = datetime.utcnow() - timedelta(hours=24)
    promos_ativas = Preco.query.filter(Preco.is_promo == True, Preco.data >= limite_promo).all()
    nomes_em_promo = [p.produto for p in promos_ativas]

    produtos_db = db.session.query(Preco.produto).distinct().all()
    sugestoes_globais = [p[0] for p in produtos_db]
    
    return render_template('listas.html', 
                           listas=minhas_listas, 
                           sugestoes_lista=sugestoes_globais,
                           promos_ativas=nomes_em_promo)

@app.route('/adicionar-item/<int:lista_id>', methods=['POST'])
@login_required
def adicionar_item(lista_id):
    nome = request.form.get('produto_nome').strip().upper()
    qtd = int(request.form.get('quantidade', 1))
    if nome:
        db.session.add(ItemLista(produto_nome=nome, quantidade=qtd, lista_id=lista_id))
        db.session.commit()
    return redirect(url_for('listas'))

@app.route('/criar-lista', methods=['POST'])
@login_required
def criar_lista():
    nome = request.form.get('nome_lista').strip()
    if nome:
        db.session.add(Lista(nome=nome, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for('listas'))

# --- COMPARAÇÃO E PROMOÇÃO ---
@app.route('/comparar')
@login_required
def comparar():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    mercados = ["Atacadão", "Extra", "Carrefour", "Pão de Açúcar"]
    rankings_finais = []

    for l in minhas_listas:
        analise_mercados = []
        for mkt in mercados:
            soma_total = 0
            encontrados = 0
            for item in l.itens:
                p_recente = Preco.query.filter_by(produto=item.produto_nome, mercado=mkt).order_by(Preco.data.desc()).first()
                if p_recente:
                    soma_total += (p_recente.valor * item.quantidade)
                    encontrados += 1
            if encontrados > 0:
                analise_mercados.append({'nome': mkt, 'total': soma_total, 'qtd_encontrados': encontrados, 'qtd_total': len(l.itens)})
        
        analise_mercados = sorted(analise_mercados, key=lambda x: x['total'])
        for i, mkt_data in enumerate(analise_mercados):
            if i == 0: mkt_data['col'] = 'text-success'; mkt_data['bg'] = 'bg-success-subtle'
            else: mkt_data['col'] = 'text-dark'; mkt_data['bg'] = 'bg-light'
        
        rankings_finais.append({'lista_nome': l.nome, 'comparativo': analise_mercados, 'tem_itens': len(l.itens) > 0})

    historico = Preco.query.order_by(Preco.data.desc()).limit(10).all()
    
    itens_usuario = db.session.query(ItemLista.produto_nome).join(Lista).filter(Lista.user_id == current_user.id).distinct().all()
    lista_sugestoes = [i[0] for i in itens_usuario]

    return render_template('comparar.html', rankings=rankings_finais, dados_comunidade=historico, sugestoes=lista_sugestoes)

@app.route('/atualizar-preco', methods=['POST'])
@login_required
def atualizar_preco():
    nome_prod = request.form.get('produto').strip().upper()
    valor_input = request.form.get('valor').replace(',', '.')
    # Verifica se veio do formulário de promoção ou comum
    is_promo = True if request.form.get('is_promo') == 'true' else False
    
    if nome_prod:
        db.session.add(Preco(produto=nome_prod, mercado=request.form.get('mercado'), valor=float(valor_input), is_promo=is_promo))
        db.session.commit()
    return redirect(url_for('comparar'))

@app.route('/alternar-item/<int:item_id>')
@login_required
def alternar_item(item_id):
    item = ItemLista.query.get_or_404(item_id)
    item.marcado = not item.marcado
    db.session.commit()
    return redirect(url_for('listas'))

if __name__ == '__main__':
    app.run(debug=True)
