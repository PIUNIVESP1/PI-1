from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chave-secreta-logistica-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///precos.db'
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELOS ---
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
    data = db.Column(db.DateTime, default=datetime.utcnow)

class Lista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    itens = db.relationship('ItemLista', backref='lista', cascade="all, delete-orphan", lazy=True)

class ItemLista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_nome = db.Column(db.String(100), nullable=False)
    quantidade = db.Column(db.Integer, default=1) # Campo de quantidade incluído
    marcado = db.Column(db.Boolean, default=False)
    lista_id = db.Column(db.Integer, db.ForeignKey('lista.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTAS DE NAVEGAÇÃO ---
@app.route('/')
@app.route('/listas')
@login_required
def listas():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    # Sugestões baseadas em preços já cadastrados por qualquer usuário
    produtos_db = db.session.query(Preco.produto).distinct().all()
    sugestoes_lista = [p[0] for p in produtos_db]
    return render_template('listas.html', listas=minhas_listas, sugestoes_lista=sugestoes_lista)

@app.route('/comparar')
@login_required
def comparar():
    minhas_listas = Lista.query.filter_by(user_id=current_user.id).all()
    mercados = ["Atacadão Santo Amaro", "Extra Moema", "Carrefour Pinheiros", "Pão de Açúcar Vila Mariana"]
    rankings_finais = []

    for l in minhas_listas:
        analise_mercados = []
        total_itens_lista = len(l.itens)
        
        if total_itens_lista > 0:
            for mkt in mercados:
                soma_total_lista = 0
                encontrados = 0
                for item in l.itens:
                    nome_limpo = item.produto_nome.strip().title()
                    p_recente = Preco.query.filter_by(produto=nome_limpo, mercado=mkt).order_by(Preco.data.desc()).first()
                    if p_recente:
                        # Lógica: Valor Unitário x Quantidade do Item
                        soma_total_lista += (p_recente.valor * item.quantidade)
                        encontrados += 1
                
                if encontrados > 0:
                    analise_mercados.append({
                        'nome': mkt, 
                        'total': soma_total_lista, 
                        'qtd_encontrados': encontrados,
                        'qtd_total': total_itens_lista
                    })
            
            # Ordenar do mais barato para o mais caro
            analise_mercados = sorted(analise_mercados, key=lambda x: x['total'])
            
            # Atribuir Cores por Posição
            for i, mkt_data in enumerate(analise_mercados):
                if i == 0: # 1º Lugar
                    mkt_data['cor'] = 'text-success'; mkt_data['bg'] = 'bg-success-subtle'
                elif i == len(analise_mercados)-1 and len(analise_mercados) > 1: # Último Lugar
                    mkt_data['cor'] = 'text-danger'; mkt_data['bg'] = 'bg-danger-subtle'
                else: # Intermediários
                    mkt_data['cor'] = 'text-warning-emphasis'; mkt_data['bg'] = 'bg-warning-subtle'

        rankings_finais.append({'lista_nome': l.nome, 'comparativo': analise_mercados})

    # Histórico geral para consulta
    precos_geral = db.session.query(Preco.produto).distinct().all()
    dados_comunidade = []
    for p in precos_geral:
        nome = p[0]
        lista_p = Preco.query.filter_by(produto=nome).order_by(Preco.valor).all()
        dados_comunidade.append({'nome': nome, 'precos': lista_p})

    return render_template('comparar.html', rankings=rankings_finais, dados_comunidade=dados_comunidade)

# --- ROTAS DE AÇÃO ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user); return redirect(url_for('listas'))
        flash('Login inválido')
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        hash_pw = generate_password_hash(request.form.get('password'))
        novo = User(username=request.form.get('username'), password=hash_pw)
        try: db.session.add(novo); db.session.commit(); return redirect(url_for('login'))
        except: flash('Usuário já existe')
    return render_template('cadastro.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/criar-lista', methods=['POST'])
@login_required
def criar_lista():
    db.session.add(Lista(nome=request.form.get('nome_lista'), user_id=current_user.id))
    db.session.commit(); return redirect(url_for('listas'))

@app.route('/adicionar-item/<int:lista_id>', methods=['POST'])
@login_required
def adicionar_item(lista_id):
    nome = request.form.get('produto_nome').strip().title()
    qtd = int(request.form.get('quantidade', 1))
    db.session.add(ItemLista(produto_nome=nome, quantidade=qtd, lista_id=lista_id))
    db.session.commit(); return redirect(url_for('listas'))

@app.route('/atualizar-preco', methods=['POST'])
@login_required
def atualizar_preco():
    db.session.add(Preco(produto=request.form.get('produto').strip().title(), mercado=request.form.get('mercado'), valor=float(request.form.get('valor'))))
    db.session.commit(); return redirect(url_for('comparar'))

@app.route('/alternar-item/<int:item_id>')
@login_required
def alternar_item(item_id):
    item = ItemLista.query.get_or_404(item_id); item.marcado = not item.marcado; db.session.commit(); return redirect(url_for('listas'))

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)
