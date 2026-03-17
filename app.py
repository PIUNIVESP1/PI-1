import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'univesp-logistica-2026-final'

# Configuração do Banco de Dados
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'precos.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- FILTRO PARA FORMATAR DATA (BR) ---
@app.template_filter('format_data')
def format_data(value):
    if not value or value == "":
        return ""
    try:
        data_obj = datetime.strptime(value, '%Y-%m-%d')
        return data_obj.strftime('%d/%m/%Y')
    except:
        return value

# --- MODELOS ---
class User(UserMixin, db.Model):
    id = db.Column(item_id := db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    listas = db.relationship('Lista', backref='dono', lazy=True)

class Preco(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto = db.Column(db.String(100), nullable=False)
    mercado = db.Column(db.String(50), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    is_promo = db.Column(db.Boolean, default=False)
    validade = db.Column(db.String(10), nullable=True) 
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

# --- ROTAS PRINCIPAIS ---

@app.route('/')
@app.route('/listas')
@login_required
def listas():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    limite = datetime.utcnow() - timedelta(hours=24)
    promos = Preco.query.filter(Preco.is_promo == True, Preco.data >= limite).all()
    dict_promos = {p.produto: p.validade for p in promos}
    
    produtos_db = db.session.query(Preco.produto).distinct().all()
    return render_template('listas.html', listas=minhas_listas, sugestoes_lista=[p[0] for p in produtos_db], promos_ativas=dict_promos)

@app.route('/comparar')
@login_required
def comparar():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    mercados = ["Atacadão", "Extra", "Carrefour", "Pão de Açúcar"]
    rankings_finais = []
    
    for l in minhas_listas:
        analise = []
        for mkt in mercados:
            soma = 0; enc = 0
            for item in l.itens:
                p = Preco.query.filter_by(produto=item.produto_nome, mercado=mkt).order_by(Preco.data.desc()).first()
                if p: soma += (p.valor * item.quantidade); enc += 1
            if enc > 0:
                analise.append({'nome': mkt, 'total': soma, 'qtd_encontrados': enc, 'qtd_total': len(l.itens)})
        
        analise = sorted(analise, key=lambda x: x['total'])
        for i, mkt_data in enumerate(analise):
            mkt_data['bg'] = 'bg-success-subtle' if i == 0 else 'bg-light'
            mkt_data['col'] = 'text-success' if i == 0 else 'text-dark'
        rankings_finais.append({'lista_nome': l.nome, 'comparativo': analise, 'tem_itens': len(l.itens) > 0})

    # Histórico mostra os últimos 20 lançamentos
    historico = Preco.query.order_by(Preco.data.desc()).limit(20).all()
    itens_usuario = db.session.query(ItemLista.produto_nome).join(Lista).filter(Lista.user_id == current_user.id).distinct().all()
    return render_template('comparar.html', rankings=rankings_finais, dados_comunidade=historico, sugestoes=[i[0] for i in itens_usuario])

# --- CRUDS E AÇÕES ---

@app.route('/atualizar-preco', methods=['POST'])
@login_required
def atualizar_preco():
    nome = request.form.get('produto').strip().upper()
    valor = request.form.get('valor').replace(',', '.')
    is_promo = request.form.get('is_promo') == 'true'
    validade = request.form.get('validade')
    
    if nome:
        db.session.add(Preco(produto=nome, mercado=request.form.get('mercado'), valor=float(valor), is_promo=is_promo, validade=validade))
        db.session.commit()
    return redirect(url_for('comparar'))

@app.route('/excluir-preco/<int:id>')
@login_required
def excluir_preco(id):
    p = Preco.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('comparar'))

@app.route('/criar-lista', methods=['POST'])
@login_required
def criar_lista():
    nome = request.form.get('nome_lista').strip()
    if nome:
        db.session.add(Lista(nome=nome, user_id=current_user.id))
        db.session.commit()
    return redirect(url_for('listas'))

@app.route('/adicionar-item/<int:lista_id>', methods=['POST'])
@login_required
def adicionar_item(lista_id):
    nome = request.form.get('produto_nome').strip().upper()
    qtd = int(request.form.get('quantidade', 1))
    if nome:
        db.session.add(ItemLista(produto_nome=nome, quantidade=qtd, lista_id=lista_id))
        db.session.commit()
    return redirect(url_for('listas'))

@app.route('/alternar-item/<int:item_id>')
@login_required
def alternar_item(item_id):
    item = ItemLista.query.get_or_404(item_id)
    item.marcado = not item.marcado
    db.session.commit()
    return redirect(url_for('listas'))

# --- AUTH ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('listas'))
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        u = request.form.get('username').strip()
        if not User.query.filter_by(username=u).first():
            novo = User(username=u, password=generate_password_hash(request.form.get('password')))
            db.session.add(novo); db.session.commit()
            return redirect(url_for('login'))
    return render_template('cadastro.html')

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
