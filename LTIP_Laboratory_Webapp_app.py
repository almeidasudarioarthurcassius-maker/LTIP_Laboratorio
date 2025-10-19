"""
LTIP Laboratory Webapp - Versão completa pronta para rede local e deploy em nuvem
Arquivo: LTIP_Laboratory_Webapp_app.py
Notas:
 - Use variáveis de ambiente para produção: SECRET_KEY, HOST, PORT, FLASK_DEBUG
 - Pastas criadas automaticamente: uploads/
 - Banco: ltip.db no mesmo diretório (SQLite)
 - Não altera o design visual
"""

import os
import socket
from datetime import datetime, timezone

from flask import (
    Flask, render_template_string, request, redirect, url_for, flash,
    send_from_directory, session, send_file
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate # <--- [ADICIONADO] Import para Flask-Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_

# ------------- Configurações -------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_DIR, "uploads")
DB_PATH = os.path.join(APP_DIR, "ltip.db")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Sensíveis via ambiente
SECRET_KEY = os.environ.get("SECRET_KEY", "troque_esta_chave_em_producao")
HOST_ENV = os.environ.get("HOST", "0.0.0.0")
PORT_ENV = int(os.environ.get("PORT", 5000))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")

# Tema (mantido)
COLOR_DARK = "#003366"
COLOR_LIGHT = "#66B2FF"
COLOR_WHITE = "#FFFFFF"

# <--- [MODIFICADO] Lógica para conexão dinâmica ao banco de dados (PostgreSQL/SQLite)
database_uri = os.environ.get("DATABASE_URL")
if database_uri:
    # Correção para o Render/SQLAlchemy: troca 'postgres://' por 'postgresql://'
    if database_uri.startswith("postgres://"):
        database_uri = database_uri.replace("postgres://", "postgresql://", 1)
else:
    # Fallback para SQLite em desenvolvimento
    database_uri = f"sqlite:///{DB_PATH}"
# ---> FIM DA MODIFICAÇÃO

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = database_uri # <--- [MODIFICADO] Usa a URI dinâmica
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB por arquivo

db = SQLAlchemy(app)
migrate = Migrate(app, db) # <--- [ADICIONADO] Inicializa o Flask-Migrate

# ------------- Models -------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, bolsista, visitor

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class LabInfo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coordenador_name = db.Column(db.String(100))
    coordenador_email = db.Column(db.String(100))
    bolsista_name = db.Column(db.String(100))
    bolsista_email = db.Column(db.String(100))

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # EQUIPAMENTO
    tombo = db.Column(db.String(100), nullable=True)
    quantidade = db.Column(db.Integer, nullable=True, default=1)
    modelo = db.Column(db.String(100), nullable=True)
    marca = db.Column(db.String(100), nullable=True)
    finalidade = db.Column(db.String(200), nullable=True)  # NOVO
    status = db.Column(db.String(100), nullable=True)
    localizacao = db.Column(db.String(200), nullable=True)
    descricao = db.Column(db.Text, nullable=True)
    imagem_filename = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # ID visível
    status = db.Column(db.String(100), nullable=False, default='Não formatado')
    tipo = db.Column(db.String(50), nullable=True)
    marca = db.Column(db.String(100), nullable=True)
    modelo = db.Column(db.String(100), nullable=True)
    numero_serie = db.Column(db.String(100), nullable=True, unique=True)
    sistema_operacional = db.Column(db.String(200), nullable=True)
    softwares_instalados = db.Column(db.Text, nullable=True)
    licencas = db.Column(db.String(255), nullable=True)
    limpeza_fisica_data = db.Column(db.Date, nullable=True)
    ultima_formatacao_data = db.Column(db.Date, nullable=True)
    responsavel_formatacao = db.Column(db.String(80), nullable=True)
    imagem_filename = db.Column(db.String(300), nullable=True)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ------------- Helpers -------------
# ... (Funções helpers inalteradas) ...

def get_status_color(status):
    if not status:
        return 'color: #666;'
    s = status.lower()
    if 'formatado' in s:
        return 'color: #1abc9c; font-weight: bold;'
    elif 'não formatado' in s or 'nao formatado' in s:
        return 'color: #e74c3c; font-weight: bold;'
    elif 'andamento' in s or 'em andamento' in s:
        return 'color: #f39c12; font-weight: bold;'
    return 'color: #666;'

def get_lab_info():
    db.session.expire_all()
    info = LabInfo.query.first()
    if not info:
        info = LabInfo(
            coordenador_name='Nome do Coordenador',
            coordenador_email='coord@exemplo.com',
            bolsista_name='Nome do Bolsista',
            bolsista_email='bolsista@exemplo.com'
        )
        db.session.add(info)
        db.session.commit()
    return info

def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None

def roles_required(allowed_roles):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = current_user()
            if not user or user.role not in allowed_roles:
                flash('Acesso negado: permissões insuficientes.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def save_uploaded_file(file_storage):
    if not file_storage:
        return None
    filename = secure_filename(file_storage.filename)
    if filename == '':
        return None
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    filename = f"{timestamp}_{filename}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_storage.save(path)
    return filename

def allowed_reports_list():
    return Report.query.order_by(Report.uploaded_at.desc()).all()

# ------------- Templates (mantive visual) -------------
# ... (Templates inalterados) ...

BASE_TEMPLATE = f"""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LTIP - Laboratório</title>
  <style>
    body{{font-family: Arial, Helvetica, sans-serif; margin:0; padding:0; background:#f6f9ff}}
    .topbar{{background:{COLOR_DARK}; color:{COLOR_WHITE}; padding:8px 20px}}
    .container{{max-width:1100px; margin:18px auto; background:#fff; padding:18px; border-radius:8px; box-shadow:0 6px 18px rgba(0,0,0,0.06)}}
    a{{color:{COLOR_LIGHT}; text-decoration:none}}
    .btn{{display:inline-block; padding:8px 12px; border-radius:6px; background:{COLOR_DARK}; color:{COLOR_WHITE}; margin-right:6px; margin-bottom:6px;}}
    .btn-outline{{border:1px solid {COLOR_LIGHT}; background:transparent; color:{COLOR_DARK}}}
    .btn-back{{background:#777; color:{COLOR_WHITE};}}
    .card{{padding:12px; border:1px solid #eef1f8; border-radius:8px}}
    table{{width:100%; border-collapse:collapse; margin-top: 15px; font-size:14px}}
    th,td{{padding:8px; border-bottom:1px solid #f0f2f5; text-align:left; vertical-align: top;}}
    .search{{margin-bottom:12px}}
    .small{{font-size:13px; color:#666}}
    .flash{{padding:10px; background:#ffe8e8; color:#900; border-radius:6px; margin-bottom:12px}}
    .right{{float:right}}
    .img-thumb{{max-width:100px; max-height:80px; object-fit: cover; border-radius:6px}}
    .muted{{color:#777}}
    .form-row{{margin-bottom:8px}}
    input,select,textarea{{width:100%; padding:8px; border-radius:6px; border:1px solid #dfe7f2}}
    .lab-title{{font-size: 24px; font-weight: bold; color: {COLOR_DARK}; margin-top: 0; margin-bottom: 15px;}}
    @media (max-width: 700px) {{
      .container{{margin:10px; padding:12px}}
      table, thead, tbody, th, td, tr {{ display:block; width:100%; }}
      thead tr {{ display:none; }}
      tr {{ margin-bottom: 12px; border-bottom: 1px solid #e9eef7; padding-bottom:10px; }}
      td {{ display:flex; justify-content:space-between; padding:6px 0; }}
      .img-thumb{{max-width:80px; max-height:60px}}
      .btn {{ padding:6px 8px; font-size:14px; }}
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="container" style="display:flex; align-items:center; justify-content:flex-end; margin:0 auto; max-width:1100px; padding: 0;">
      <div>
        {{% if user %}}
          Olá, <strong>{{{{ user.username }}}}</strong> ({{{{ user.role }}}})
          <a href="{{{{ url_for('logout') }}}}" class="btn btn-outline" style="border-color: {COLOR_WHITE}; color: {COLOR_WHITE};">Sair</a>
        {{% else %}}
          <a href="{{{{ url_for('login') }}}}" class="btn">Entrar</a>
        {{% endif %}}
      </div>
    </div>
  </div>
  <div class="container">
    <h1 class="lab-title">LABORATÓRIO DE TECNOLOGIA DA INFORMAÇÃO DO PROFÁGUA - LTIP</h1>
    {{% with messages = get_flashed_messages(with_categories=true) %}}
      {{% if messages %}}
        {{% for cat,msg in messages %}}
          <div class="flash">{{{{ msg }}}}</div>
        {{% endfor %}}
      {{% endif %}}
    {{% endwith %}}
    __CONTENT_BLOCK__
    <hr>
    <div class="small muted">Gerenciado por administrador e bolsista.</div>
  </div>
</body>
</html>
"""

# ... (Templates inalterados) ...

INDEX_TEMPLATE = r"""
<h2>Bem-vindo ao Laboratório</h2>
<p>Use o menu abaixo para navegar.</p>
<div style="margin-bottom:12px">
  <a href="{{ url_for('inventory') }}" class="btn">Inventário</a>
  <a href="{{ url_for('machine_inventory') }}" class="btn">Gerenciamento de Máquinas</a>
  <a href="{{ url_for('reports') }}" class="btn">Relatórios</a>
  {% if user and user.role in ['admin','bolsista'] %}
    <a href="{{ url_for('add_equipment') }}" class="btn btn-outline">Cadastrar Equipamento</a>
    <a href="{{ url_for('add_machine') }}" class="btn btn-outline">Cadastrar Máquina</a>
    <a href="{{ url_for('upload_report') }}" class="btn btn-outline">Enviar Relatório</a>
  {% endif %}
  <a href="{{ url_for('lab_info') }}" class="btn btn-outline">Configurações do Laboratório</a>
</div>
<div class="card">
  <h3>Informações de Contato</h3>
  <p>Coordenador: <strong>{{ info.coordenador_name }}</strong> ({{ info.coordenador_email }})</p>
  <p>Bolsista: <strong>{{ info.bolsista_name }}</strong> ({{ info.bolsista_email }})</p>
  <p>Descrição: Sistema de controle de inventário desenvolvido para o LTIP.</p>
</div>
"""

INVENTORY_TEMPLATE = r"""
<a href="{{ url_for('index') }}" class="btn btn-back">← Voltar</a>
<h2>Inventário de Equipamentos</h2>

<form method="get" style="margin-top:8px; display:flex; gap:8px; align-items:center;">
  <input name="q" placeholder="Buscar por equipamento, marca, modelo, tombo ou finalidade..." value="{{ request.args.get('q','') }}">
  <button class="btn">Buscar</button>
  <a href="{{ url_for('inventory') }}" class="btn btn-outline">Limpar</a>
</form>

<table>
  <thead>
    <tr>
      <th>IMAGEM</th>
      <th>EQUIPAMENTO</th>
      <th>TOMBO</th>
      <th>MARCA</th>
      <th>MODELO</th>
      <th>QUANTIDADE</th>
      <th>LOCALIZAÇÃO</th>
      <th>FINALIDADE</th>
      <th>Ações</th>
    </tr>
  </thead>
  <tbody>
    {% for e in items %}
      <tr>
        <td>{% if e.imagem_filename %}<img class="img-thumb" src="{{ url_for('uploaded_file', filename=e.imagem_filename) }}">{% else %}-{% endif %}</td>
        <td>{{ e.name }}</td>
        <td>{{ e.tombo }}</td>
        <td>{{ e.marca }}</td>
        <td>{{ e.modelo }}</td>
        <td>{{ e.quantidade }}</td>
        <td>{{ e.localizacao }}</td>
        <td>{{ e.finalidade }}</td>
        <td>
          <a href="{{ url_for('view_equipment', eq_id=e.id) }}">Ver</a>
          {% if user and user.role in ['admin','bolsista'] %} | <a href="{{ url_for('edit_equipment', eq_id=e.id) }}">Editar</a>{% endif %}
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>
"""

ADD_EDIT_EQUIPMENT_TEMPLATE = r"""
<a href="{{ url_for('inventory') }}" class="btn btn-back">← Voltar</a>
<h2>{{ 'Editar' if edit else 'Cadastrar' }} Equipamento</h2>
<form method="post" enctype="multipart/form-data" style="margin-top: 15px;">
  <div class="form-row"><label>Nome / Equipamento</label><input name="name" required value="{{ item.name if item else '' }}"></div>
  <div style="display: flex; gap: 15px;">
    <div class="form-row" style="flex: 1;"><label>Marca</label><input name="marca" value="{{ item.marca if item else '' }}"></div>
    <div class="form-row" style="flex: 1;"><label>Modelo</label><input name="modelo" value="{{ item.modelo if item else '' }}"></div>
  </div>
  <div style="display: flex; gap: 15px;">
    <div class="form-row" style="flex: 1;"><label>TOMBO (Nº de Patrimônio)</label><input name="tombo" value="{{ item.tombo if item else '' }}"></div>
    <div class="form-row" style="flex: 1;"><label>Quantidade</label><input name="quantidade" type="number" min="1" value="{{ item.quantidade if item else 1 }}"></div>
  </div>
  <div class="form-row"><label>Localização</label><input name="localizacao" value="{{ item.localizacao if item else '' }}"></div>
  <div class="form-row"><label>Finalidade</label><input name="finalidade" value="{{ item.finalidade if item else '' }}"></div>
  <div class="form-row"><label>Imagem (Opcional)</label><input type="file" name="imagem"></div>
  <div class="form-row"><button class="btn">Salvar</button></div>
</form>
"""

MACHINE_INVENTORY_TEMPLATE = r"""
<a href="{{ url_for('index') }}" class="btn btn-back">← Voltar</a>
<h2>Gerenciamento de Máquinas (Computadores/Notebooks)</h2>
{% if user and user.role in ['admin','bolsista'] %}
<p><a href="{{ url_for('add_machine') }}" class="btn">Cadastrar Nova Máquina</a></p>
{% endif %}

<form method="get" style="margin-top:8px; display:flex; gap:8px; align-items:center;">
  <input name="q" placeholder="Buscar por ID, marca, modelo, N/S, SO, licença..." value="{{ request.args.get('q','') }}">
  <button class="btn">Buscar</button>
  <a href="{{ url_for('machine_inventory') }}" class="btn btn-outline">Limpar</a>
</form>

<table>
  <thead>
    <tr>
      <th>IMAGEM</th>
      <th>ID</th>
      <th>Tipo</th>
      <th>Marca</th>
      <th>Modelo</th>
      <th>Sistema Operacional</th>
      <th>Licença</th>
      <th>Status</th>
      <th>Última Limpeza Física</th>
      <th>Última Formatação</th>
      <th>Ações</th>
    </tr>
  </thead>
  <tbody>
    {% for m in items %}
      <tr>
        <td>{% if m.imagem_filename %}<img class="img-thumb" src="{{ url_for('uploaded_file', filename=m.imagem_filename) }}">{% else %}-{% endif %}</td>
        <td>{{ m.name }}</td>
        <td>{{ m.tipo }}</td>
        <td>{{ m.marca }}</td>
        <td>{{ m.modelo }}</td>
        <td>{{ m.sistema_operacional }}</td>
        <td>{{ m.licencas }}</td>
        <td style="{{ get_status_color(m.status) }}">{{ m.status }}</td>
        <td>{{ m.limpeza_fisica_data | default('N/A', true) }}</td>
        <td>{{ m.ultima_formatacao_data | default('N/A', true) }}</td>
        <td>
          <a href="{{ url_for('view_machine', machine_id=m.id) }}">Ver</a>
          {% if user and user.role in ['admin','bolsista'] %} | <a href="{{ url_for('edit_machine', machine_id=m.id) }}">Editar</a>{% endif %}
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>
"""

ADD_EDIT_MACHINE_TEMPLATE = r"""
<a href="{{ url_for('machine_inventory') }}" class="btn btn-back">← Voltar</a>
<h2>{{ 'Editar' if edit else 'Cadastrar' }} Máquina</h2>
<form method="post" enctype="multipart/form-data" style="margin-top: 15px;">
  <div class="form-row"><label>ID / Nome da Máquina (ex: PC 01)</label><input name="name" required value="{{ item.name if item else '' }}"></div>
  <div style="display: flex; gap: 15px;">
    <div class="form-row" style="flex: 1;"><label>Tipo</label>
        <select name="tipo">
            {% set current_tipo = item.tipo if item else '' %}
            <option value="COMPUTADOR" {% if current_tipo == 'COMPUTADOR' %}selected{% endif %}>COMPUTADOR</option>
            <option value="NOTEBOOK" {% if current_tipo == 'NOTEBOOK' %}selected{% endif %}>NOTEBOOK</option>
        </select>
    </div>
    <div class="form-row" style="flex: 1;"><label>Status</label>
        <select name="status" required>
            {% set current_status = item.status if item else 'Não formatado' %}
            <option value="Formatado" {% if current_status == 'Formatado' %}selected{% endif %}>Formatado (Cor Verde)</option>
            <option value="Não formatado" {% if current_status == 'Não formatado' %}selected{% endif %}>Não formatado (Cor Vermelho)</option>
            <option value="Em andamento" {% if current_status == 'Em andamento' %}selected{% endif %}>Em andamento (Cor Amarelo)</option>
        </select>
    </div>
  </div>

  <div style="display:flex; gap:15px;">
    <div class="form-row" style="flex:1;"><label>Marca</label><input name="marca" value="{{ item.marca if item else '' }}"></div>
    <div class="form-row" style="flex:1;"><label>Modelo</label><input name="modelo" value="{{ item.modelo if item else '' }}"></div>
  </div>

  <div class="form-row"><label>Número de Série</label><input name="numero_serie" required value="{{ item.numero_serie if item else '' }}"></div>
  <div class="form-row"><label>Sistema Operacional</label><input name="sistema_operacional" value="{{ item.sistema_operacional if item else '' }}"></div>
  <div class="form-row"><label>Licença / Observações sobre licença</label><input name="licencas" value="{{ item.licencas if item else '' }}"></div>
  <div style="display:flex; gap:15px;">
    <div class="form-row" style="flex:1;"><label>Última Limpeza Física</label><input name="limpeza_fisica_data" type="date" value="{{ item.limpeza_fisica_data | default('', true) }}"></div>
    <div class="form-row" style="flex:1;"><label>Última Formatação</label><input name="ultima_formatacao_data" type="date" value="{{ item.ultima_formatacao_data | default('', true) }}"></div>
  </div>

  <div class="form-row"><label>Responsável pela Formatação</label><input name="responsavel_formatacao" value="{{ item.responsavel_formatacao if item else '' }}"></div>
  <div class="form-row"><label>Imagem (Opcional)</label><input type="file" name="imagem"></div>

  <div class="form-row"><button class="btn">Salvar</button></div>
</form>
"""

LAB_INFO_TEMPLATE = r"""
<a href="{{ url_for('index') }}" class="btn btn-back">← Voltar</a>
<h2>Configurações e Contatos do Laboratório</h2>
<form method="post" style="margin-top: 15px;">
  <p style="font-weight: bold; margin-bottom: 5px;">Informações do Coordenador</p>
  <div class="form-row"><label>Nome do Coordenador</label><input name="coordenador_name" required value="{{ info.coordenador_name }}"></div>
  <div class="form-row"><label>Email do Coordenador</label><input name="coordenador_email" type="email" value="{{ info.coordenador_email }}"></div>
  
  <p style="font-weight: bold; margin-top: 15px; margin-bottom: 5px;">Informações do Bolsista</p>
  <div class="form-row"><label>Nome do Bolsista</label><input name="bolsista_name" required value="{{ info.bolsista_name }}"></div>
  <div class="form-row"><label>Email do Bolsista</label><input name="bolsista_email" type="email" value="{{ info.bolsista_email }}"></div>
  
  <div class="form-row"><button class="btn">Salvar Configurações</button> <a href="{{ url_for('index') }}" class="btn btn-outline">Cancelar</a></div>
</form>
"""

REPORTS_TEMPLATE = r"""
<a href="{{ url_for('index') }}" class="btn btn-back">← Voltar</a>
<h2>Relatórios Mensais</h2>

{% if user and user.role in ['admin','bolsista'] %}
  <p><a href="{{ url_for('upload_report') }}" class="btn">Enviar Relatório</a></p>
{% endif %}

<table>
  <thead>
    <tr><th>TÍTULO</th><th>ARQUIVO</th><th>ENVIADO EM</th><th>AÇÕES</th></tr>
  </thead>
  <tbody>
    {% for r in reports %}
      <tr>
        <td>{{ r.title }}</td>
        <td>{{ r.filename }}</td>
        <td>{{ r.uploaded_at }}</td>
        <td>
          <a href="{{ url_for('download_report', report_id=r.id) }}">Download</a>
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>
"""

UPLOAD_REPORT_TEMPLATE = r"""
<a href="{{ url_for('reports') }}" class="btn btn-back">← Voltar</a>
<h2>Enviar Relatório</h2>
<form method="post" enctype="multipart/form-data" style="margin-top:15px;">
  <div class="form-row"><label>Título</label><input name="title" required></div>
  <div class="form-row"><label>Arquivo (PDF/DOCX)</label><input type="file" name="report_file" accept=".pdf,.docx,.doc"></div>
  <div class="form-row"><button class="btn">Enviar</button></div>
</form>
"""

# ------------- Rotas -------------
# ... (Rotas inalteradas) ...

@app.route("/")
def index():
    info = get_lab_info()
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", INDEX_TEMPLATE)
    return render_template_string(final_template, user=current_user(), info=info)

# --- Auth ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash("Logado com sucesso.", "success")
            return redirect(url_for("index"))
        flash("Usuário ou senha inválidos.", "danger")
    template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", """
        <h2>Login</h2>
        <form method="post">
            <div class="form-row"><input name="username" placeholder="Usuário" required></div>
            <div class="form-row"><input name="password" placeholder="Senha" type="password" required></div>
            <div class="form-row"><button class="btn">Entrar</button></div>
        </form>
    """)
    return render_template_string(template, user=current_user())

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logout realizado.", "success")
    return redirect(url_for("index"))

# --- Lab Info (edição atualiza imediatamente) ---
@app.route("/lab_info", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def lab_info():
    info = get_lab_info()
    if request.method == "POST":
        info.coordenador_name = request.form.get("coordenador_name")
        info.coordenador_email = request.form.get("coordenador_email")
        info.bolsista_name = request.form.get("bolsista_name")
        info.bolsista_email = request.form.get("bolsista_email")
        db.session.commit()
        db.session.expire_all()
        flash("Informações do Laboratório atualizadas.", "success")
        return redirect(url_for("index"))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", LAB_INFO_TEMPLATE)
    return render_template_string(final_template, user=current_user(), info=info)

# --- Inventory ---
@app.route("/inventory")
def inventory():
    q = (request.args.get("q") or "").strip()
    query = Equipment.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Equipment.name.ilike(like),
                Equipment.marca.ilike(like),
                Equipment.modelo.ilike(like),
                Equipment.tombo.ilike(like),
                Equipment.finalidade.ilike(like),
            )
        )
    items = query.order_by(Equipment.name).all()
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", INVENTORY_TEMPLATE)
    return render_template_string(final_template, user=current_user(), items=items, request=request)

@app.route("/equipment/add", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def add_equipment():
    if request.method == "POST":
        try:
            quantidade = int(request.form.get("quantidade") or 1)
        except ValueError:
            quantidade = 1
        imagem = request.files.get("imagem")
        saved = save_uploaded_file(imagem)
        eq = Equipment(
            name=request.form.get("name"),
            tombo=request.form.get("tombo"),
            quantidade=quantidade,
            modelo=request.form.get("modelo"),
            marca=request.form.get("marca"),
            localizacao=request.form.get("localizacao"),
            finalidade=request.form.get("finalidade"),
            imagem_filename=saved,
        )
        db.session.add(eq)
        db.session.commit()
        flash("Equipamento cadastrado com sucesso.", "success")
        return redirect(url_for("inventory"))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", ADD_EDIT_EQUIPMENT_TEMPLATE)
    return render_template_string(final_template, user=current_user(), edit=False, item=None)

@app.route("/equipment/<int:eq_id>")
def view_equipment(eq_id):
    item = Equipment.query.get_or_404(eq_id)
    body = f"""
    <a href="{{{{ url_for('inventory') }}}}" class="btn btn-back">← Voltar</a>
    <h2>Detalhes do Equipamento: {item.name}</h2>
    <p><strong>TOMBO:</strong> {item.tombo}</p>
    <p><strong>Quantidade:</strong> {item.quantidade}</p>
    <p><strong>Marca:</strong> {item.marca}</p>
    <p><strong>Modelo:</strong> {item.modelo}</p>
    <p><strong>Localização:</strong> {item.localizacao}</p>
    <p><strong>Finalidade:</strong> {item.finalidade}</p>
    """
    if item.imagem_filename:
        body += f'<p><strong>Imagem:</strong><br><img class="img-thumb" src="{{{{ url_for(\'uploaded_file\', filename=\'{item.imagem_filename}\') }}}}"></p>'
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", body)
    return render_template_string(final_template, user=current_user(), item=item)

@app.route("/equipment/edit/<int:eq_id>", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def edit_equipment(eq_id):
    item = Equipment.query.get_or_404(eq_id)
    if request.method == "POST":
        try:
            item.quantidade = int(request.form.get("quantidade") or 1)
        except ValueError:
            item.quantidade = 1
        item.name = request.form.get("name")
        item.tombo = request.form.get("tombo")
        item.modelo = request.form.get("modelo")
        item.marca = request.form.get("marca")
        item.localizacao = request.form.get("localizacao")
        item.finalidade = request.form.get("finalidade")
        imagem = request.files.get("imagem")
        saved = save_uploaded_file(imagem)
        if saved:
            item.imagem_filename = saved
        db.session.commit()
        flash("Atualizado com sucesso.", "success")
        return redirect(url_for("view_equipment", eq_id=item.id))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", ADD_EDIT_EQUIPMENT_TEMPLATE)
    return render_template_string(final_template, user=current_user(), edit=True, item=item)

# --- Machines ---
@app.route("/machines")
def machine_inventory():
    q = (request.args.get("q") or "").strip()
    query = Machine.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Machine.name.ilike(like),
                Machine.marca.ilike(like),
                Machine.modelo.ilike(like),
                Machine.numero_serie.ilike(like),
                Machine.sistema_operacional.ilike(like),
                Machine.licencas.ilike(like),
            )
        )
    items = query.order_by(Machine.name).all()
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", MACHINE_INVENTORY_TEMPLATE)
    return render_template_string(final_template, user=current_user(), items=items, get_status_color=get_status_color, request=request)

@app.route("/machine/add", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def add_machine():
    if request.method == "POST":
        def parse_date_str(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date() if s else None
            except Exception:
                return None
        ultima_formatacao = parse_date_str(request.form.get("ultima_formatacao_data"))
        limpeza_data = parse_date_str(request.form.get("limpeza_fisica_data"))

        if request.form.get("numero_serie") and Machine.query.filter_by(numero_serie=request.form.get("numero_serie")).first():
            flash("Erro: Número de Série já cadastrado.", "danger")
            return redirect(url_for("add_machine"))

        imagem = request.files.get("imagem")
        saved = save_uploaded_file(imagem)

        m = Machine(
            name=request.form.get("name"),
            status=request.form.get("status"),
            tipo=request.form.get("tipo"),
            numero_serie=request.form.get("numero_serie"),
            ultima_formatacao_data=ultima_formatacao,
            limpeza_fisica_data=limpeza_data,
            responsavel_formatacao=request.form.get("responsavel_formatacao"),
            marca=request.form.get("marca"),
            modelo=request.form.get("modelo"),
            sistema_operacional=request.form.get("sistema_operacional"),
            licencas=request.form.get("licencas"),
            imagem_filename=saved,
        )
        db.session.add(m)
        db.session.commit()
        flash("Máquina cadastrada com sucesso.", "success")
        return redirect(url_for("machine_inventory"))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", ADD_EDIT_MACHINE_TEMPLATE)
    return render_template_string(final_template, user=current_user(), edit=False, item=None)

@app.route("/machine/edit/<int:machine_id>", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def edit_machine(machine_id):
    item = Machine.query.get_or_404(machine_id)
    if request.method == "POST":
        def parse_date_str(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date() if s else None
            except Exception:
                return None
        ultima_formatacao = parse_date_str(request.form.get("ultima_formatacao_data"))
        limpeza_data = parse_date_str(request.form.get("limpeza_fisica_data"))

        if request.form.get("numero_serie") and Machine.query.filter(Machine.numero_serie == request.form.get("numero_serie"), Machine.id != machine_id).first():
            flash("Erro: Número de Série já cadastrado em outra máquina.", "danger")
            return redirect(url_for("edit_machine", machine_id=machine_id))

        item.name = request.form.get("name")
        item.status = request.form.get("status")
        item.tipo = request.form.get("tipo")
        item.numero_serie = request.form.get("numero_serie")
        item.ultima_formatacao_data = ultima_formatacao
        item.limpeza_fisica_data = limpeza_data
        item.responsavel_formatacao = request.form.get("responsavel_formatacao")
        item.marca = request.form.get("marca")
        item.modelo = request.form.get("modelo")
        item.sistema_operacional = request.form.get("sistema_operacional")
        item.licencas = request.form.get("licencas")

        imagem = request.files.get("imagem")
        saved = save_uploaded_file(imagem)
        if saved:
            item.imagem_filename = saved

        db.session.commit()
        flash("Máquina atualizada com sucesso.", "success")
        return redirect(url_for("view_machine", machine_id=item.id))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", ADD_EDIT_MACHINE_TEMPLATE)
    return render_template_string(final_template, user=current_user(), edit=True, item=item)

@app.route("/machine/<int:machine_id>")
def view_machine(machine_id):
    item = Machine.query.get_or_404(machine_id)
    body = f"""
    <a href="{{{{ url_for('machine_inventory') }}}}" class="btn btn-back">← Voltar</a>
    <h2>Detalhes da Máquina: {item.name}</h2>
    <p><strong>Status:</strong> <span style="{get_status_color(item.status)}">{item.status}</span></p>
    <p><strong>Tipo:</strong> {item.tipo}</p>
    <p><strong>Marca:</strong> {item.marca or 'N/A'}</p>
    <p><strong>Modelo:</strong> {item.modelo or 'N/A'}</p>
    <p><strong>Número de Série:</strong> {item.numero_serie or 'N/A'}</p>
    <p><strong>Sistema Operacional:</strong> {item.sistema_operacional or 'N/A'}</p>
    <p><strong>Licença:</strong> {item.licencas or 'N/A'}</p>
    <p><strong>Última Limpeza Física:</strong> {item.limpeza_fisica_data or 'N/A'}</p>
    <p><strong>Última Formatação:</strong> {item.ultima_formatacao_data or 'N/A'}</p>
    <p><strong>Responsável:</strong> {item.responsavel_formatacao or 'N/A'}</p>
    """
    if item.imagem_filename:
        body += f'<p><strong>Imagem:</strong><br><img class="img-thumb" src="{{{{ url_for(\'uploaded_file\', filename=\'{item.imagem_filename}\') }}}}"></p>'
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", body)
    return render_template_string(final_template, user=current_user(), item=item, get_status_color=get_status_color)

# --- Upload serve ---
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- Reports ---
@app.route("/reports")
def reports():
    reports = allowed_reports_list()
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", REPORTS_TEMPLATE)
    return render_template_string(final_template, user=current_user(), reports=reports)

@app.route("/reports/upload", methods=["GET", "POST"])
@roles_required(["admin", "bolsista"])
def upload_report():
    if request.method == "POST":
        title = request.form.get("title") or "Relatório"
        file = request.files.get("report_file")
        if not file:
            flash("Selecione um arquivo para enviar.", "danger")
            return redirect(url_for("upload_report"))
        saved = save_uploaded_file(file)
        if not saved:
            flash("Falha ao salvar o arquivo.", "danger")
            return redirect(url_for("upload_report"))
        rpt = Report(title=title, filename=saved)
        db.session.add(rpt)
        db.session.commit()
        flash("Relatório enviado com sucesso.", "success")
        return redirect(url_for("reports"))
    final_template = BASE_TEMPLATE.replace("__CONTENT_BLOCK__", UPLOAD_REPORT_TEMPLATE)
    return render_template_string(final_template, user=current_user())

@app.route("/reports/download/<int:report_id>")
def download_report(report_id):
    rpt = Report.query.get_or_404(report_id)
    path = os.path.join(app.config["UPLOAD_FOLDER"], rpt.filename)
    if not os.path.exists(path):
        flash("Arquivo não encontrado.", "danger")
        return redirect(url_for("reports"))
    return send_file(path, as_attachment=True, download_name=rpt.filename)

# ------------- DB init & defaults -------------
def init_db_and_create_default_users():
    with app.app_context():
        # db_exists = os.path.exists(DB_PATH) # LINHA REMOVIDA
        # db.create_all() # <--- [REMOVIDO] Migrações (Flask-Migrate) farão este trabalho.
        
        # Create default users if none exist
        if User.query.count() == 0:
            admin = User(username="rendeiro123", role="admin")
            admin.set_password("admLTIP2025")
            bols = User(username="arthur123", role="bolsista")
            bols.set_password("LTIP2025")
            visitor = User(username="visitante", role="visitor")
            visitor.set_password("visitante123")
            db.session.add_all([admin, bols, visitor])
            db.session.commit()
        if LabInfo.query.count() == 0:
            info = LabInfo(
                coordenador_name="Nome do Coordenador",
                coordenador_email="coord@exemplo.com",
                bolsista_name="Nome do Bolsista",
                bolsista_email="bolsista@exemplo.com",
            )
            db.session.add(info)
            db.session.commit()

# ------------- Execução principal -------------
if __name__ == "__main__":
    with app.app_context():
        init_db_and_create_default_users()

    # Tenta detectar IP local amigável para exibir (não altera host)
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
    except Exception:
        local_ip = None

    print("==========================================")
    print(" LTIP Laboratory WebApp - Iniciando")
    print("==========================================")
    if local_ip:
        print(f"Acessível na rede local: http://{local_ip}:{PORT_ENV}")
    print(f"Acessível em todas interfaces na porta: {PORT_ENV}")
    print("Para deploy em nuvem, defina variáveis de ambiente: SECRET_KEY, PORT, FLASK_DEBUG (True/False)")
    print("==========================================")

    # Executa o app (pronto para rede local e para ambientes de nuvem que definem PORT)
    app.run(host=HOST_ENV, port=PORT_ENV, debug=FLASK_DEBUG)
