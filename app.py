from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, date
import bcrypt
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gestbulletin-secret-2024-malicksy')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gestbulletin.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ══════════════════════════════════════════
#  MODÈLES DE BASE DE DONNÉES
# ══════════════════════════════════════════

class Utilisateur(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(50), unique=True, nullable=False)
    mot_de_passe = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # directeur, censeur, enseignant, secretaire, eleve
    actif = db.Column(db.Boolean, default=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey('eleve.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, pwd):
        return bcrypt.checkpw(pwd.encode('utf-8'), self.mot_de_passe.encode('utf-8'))

    def get_id(self):
        return str(self.id)

class Classe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(50), nullable=False)
    niveau = db.Column(db.String(20))
    serie = db.Column(db.String(20))
    prof_principal = db.Column(db.String(100))
    annee_scolaire = db.Column(db.String(10), default='2024-2025')
    eleves = db.relationship('Eleve', backref='classe', lazy=True)

class Eleve(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(50), nullable=False)
    prenom = db.Column(db.String(50), nullable=False)
    sexe = db.Column(db.String(1), default='M')
    date_naissance = db.Column(db.Date)
    matricule = db.Column(db.String(30), unique=True)
    contact_parent = db.Column(db.String(30))
    classe_id = db.Column(db.Integer, db.ForeignKey('classe.id'))
    notes = db.relationship('Note', backref='eleve', lazy=True, cascade='all, delete-orphan')
    absences = db.relationship('Absence', backref='eleve', lazy=True, cascade='all, delete-orphan')

class Matiere(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    groupe = db.Column(db.String(100))
    coefficient = db.Column(db.Float, default=1.0)
    enseignant = db.Column(db.String(100))
    notes = db.relationship('Note', backref='matiere', lazy=True)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey('eleve.id'), nullable=False)
    matiere_id = db.Column(db.Integer, db.ForeignKey('matiere.id'), nullable=False)
    trimestre = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Absence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey('eleve.id'), nullable=False)
    matiere_id = db.Column(db.Integer, db.ForeignKey('matiere.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    heure_debut = db.Column(db.String(5))
    heure_fin = db.Column(db.String(5))
    statut = db.Column(db.String(20), default='injustifiee')  # justifiee, injustifiee, en_attente
    motif = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Demande(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    eleve_id = db.Column(db.Integer, db.ForeignKey('eleve.id'), nullable=False)
    type_demande = db.Column(db.String(30))  # absence, sortie, rattrapage, autre
    date_concernee = db.Column(db.Date)
    motif = db.Column(db.Text)
    statut = db.Column(db.String(20), default='attente')  # attente, approuvee, refusee
    traite_par = db.Column(db.String(100))
    date_traitement = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    eleve = db.relationship('Eleve', backref='demandes')

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cle = db.Column(db.String(50), unique=True, nullable=False)
    valeur = db.Column(db.String(200))

# ══════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════

@login_manager.user_loader
def load_user(user_id):
    return Utilisateur.query.get(int(user_id))

def role_requis(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role not in roles:
                return jsonify({'erreur': 'Accès non autorisé'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

def get_config(cle, defaut=''):
    c = Config.query.filter_by(cle=cle).first()
    return c.valeur if c else defaut

def hash_password(pwd):
    return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def calc_moyenne(eleve_id, trimestre):
    notes = Note.query.filter_by(eleve_id=eleve_id, trimestre=trimestre).all()
    if not notes:
        return None
    total_pts = sum(n.note * n.matiere.coefficient for n in notes)
    total_coef = sum(n.matiere.coefficient for n in notes)
    return round(total_pts / total_coef, 2) if total_coef > 0 else None

def get_mention(moy):
    if moy is None: return ('—', '')
    if moy >= 16: return ('Très Bien', 'tb')
    if moy >= 14: return ('Bien', 'bi')
    if moy >= 12: return ('Assez Bien', 'ab')
    if moy >= 10: return ('Passable', 'pa')
    if moy >= 8:  return ('Insuffisant', 'in')
    return ('Élim. Impossible', 'ei')

def calc_heures_abs(eleve_id):
    absences = Absence.query.filter_by(eleve_id=eleve_id).all()
    total = 0
    for a in absences:
        if a.heure_debut and a.heure_fin:
            hd, md = map(int, a.heure_debut.split(':'))
            hf, mf = map(int, a.heure_fin.split(':'))
            total += (hf * 60 + mf - hd * 60 - md) / 60
        else:
            total += 2
    return round(total, 1)

# ══════════════════════════════════════════
#  ROUTES AUTH
# ══════════════════════════════════════════

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'eleve':
            return redirect(url_for('portal_notes'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        login_val = data.get('login', '').strip()
        password = data.get('password', '')
        user = Utilisateur.query.filter_by(login=login_val, actif=True).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            if request.is_json:
                return jsonify({'succes': True, 'role': user.role})
            return redirect(url_for('index'))
        if request.is_json:
            return jsonify({'erreur': 'Identifiant ou mot de passe incorrect'}), 401
        flash('Identifiant ou mot de passe incorrect', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ══════════════════════════════════════════
#  PAGES PRINCIPALES
# ══════════════════════════════════════════

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'eleve':
        return redirect(url_for('portal_notes'))
    nb_eleves = Eleve.query.count()
    nb_classes = Classe.query.count()
    now = datetime.now()
    abs_mois = Absence.query.filter(
        db.extract('month', Absence.date) == now.month,
        db.extract('year', Absence.date) == now.year
    ).count()
    abs_ij = Absence.query.filter(
        db.extract('month', Absence.date) == now.month,
        Absence.statut == 'injustifiee'
    ).count()
    dem_attente = Demande.query.filter_by(statut='attente').count()

    # Top 5
    eleves = Eleve.query.all()
    palmares = []
    for e in eleves:
        moy = calc_moyenne(e.id, 1)
        if moy is not None:
            palmares.append({'eleve': e, 'moy': moy, 'classe': e.classe})
    palmares.sort(key=lambda x: x['moy'], reverse=True)
    palmares = palmares[:5]

    return render_template('dashboard.html',
        nb_eleves=nb_eleves, nb_classes=nb_classes,
        abs_mois=abs_mois, abs_ij=abs_ij,
        dem_attente=dem_attente, palmares=palmares,
        cfg_nom=get_config('nom', 'Lycée Malick Sy'))

# ══════════════════════════════════════════
#  API ÉLÈVES
# ══════════════════════════════════════════

@app.route('/api/eleves', methods=['GET'])
@login_required
def api_eleves():
    q = request.args.get('q', '')
    classe_id = request.args.get('classe_id')
    query = Eleve.query
    if q:
        query = query.filter(db.or_(Eleve.nom.ilike(f'%{q}%'), Eleve.prenom.ilike(f'%{q}%')))
    if classe_id:
        query = query.filter_by(classe_id=int(classe_id))
    eleves = query.order_by(Eleve.nom).all()
    return jsonify([{
        'id': e.id, 'nom': e.nom, 'prenom': e.prenom, 'sexe': e.sexe,
        'matricule': e.matricule or '—',
        'date_naissance': e.date_naissance.strftime('%d/%m/%Y') if e.date_naissance else '—',
        'classe': e.classe.nom if e.classe else '—',
        'classe_id': e.classe_id,
        'heures_abs': calc_heures_abs(e.id),
        'abs_ij': Absence.query.filter_by(eleve_id=e.id, statut='injustifiee').count()
    } for e in eleves])

@app.route('/api/eleves', methods=['POST'])
@login_required
@role_requis('directeur', 'censeur', 'secretaire')
def api_add_eleve():
    d = request.get_json()
    mat = d.get('matricule', '').strip()
    if mat and Eleve.query.filter_by(matricule=mat).first():
        return jsonify({'erreur': 'Ce matricule existe déjà'}), 400
    ddn = None
    if d.get('date_naissance'):
        try: ddn = datetime.strptime(d['date_naissance'], '%Y-%m-%d').date()
        except: pass
    e = Eleve(nom=d['nom'].upper().strip(), prenom=d['prenom'].strip(),
              sexe=d.get('sexe', 'M'), date_naissance=ddn,
              matricule=mat or None, contact_parent=d.get('contact_parent', ''),
              classe_id=int(d['classe_id']) if d.get('classe_id') else None)
    db.session.add(e)
    db.session.commit()
    # Créer compte élève automatiquement
    if mat:
        pwd = d.get('password', mat)
        u = Utilisateur(nom=e.nom+' '+e.prenom, login=mat,
                        mot_de_passe=hash_password(pwd), role='eleve', eleve_id=e.id)
        db.session.add(u)
        db.session.commit()
    return jsonify({'succes': True, 'id': e.id})

@app.route('/api/eleves/<int:eid>', methods=['PUT'])
@login_required
@role_requis('directeur', 'censeur', 'secretaire')
def api_update_eleve(eid):
    e = Eleve.query.get_or_404(eid)
    d = request.get_json()
    e.nom = d.get('nom', e.nom).upper().strip()
    e.prenom = d.get('prenom', e.prenom).strip()
    e.sexe = d.get('sexe', e.sexe)
    e.contact_parent = d.get('contact_parent', e.contact_parent)
    if d.get('classe_id'): e.classe_id = int(d['classe_id'])
    if d.get('date_naissance'):
        try: e.date_naissance = datetime.strptime(d['date_naissance'], '%Y-%m-%d').date()
        except: pass
    db.session.commit()
    return jsonify({'succes': True})

@app.route('/api/eleves/<int:eid>', methods=['DELETE'])
@login_required
@role_requis('directeur', 'censeur')
def api_delete_eleve(eid):
    e = Eleve.query.get_or_404(eid)
    Utilisateur.query.filter_by(eleve_id=eid).delete()
    db.session.delete(e)
    db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API CLASSES
# ══════════════════════════════════════════

@app.route('/api/classes', methods=['GET'])
@login_required
def api_classes():
    classes = Classe.query.all()
    return jsonify([{'id': c.id, 'nom': c.nom, 'niveau': c.niveau or '—',
                     'serie': c.serie or '—', 'prof_principal': c.prof_principal or '—',
                     'effectif': len(c.eleves)} for c in classes])

@app.route('/api/classes', methods=['POST'])
@login_required
@role_requis('directeur', 'censeur', 'secretaire')
def api_add_classe():
    d = request.get_json()
    c = Classe(nom=d['nom'].strip(), niveau=d.get('niveau', ''), serie=d.get('serie', ''),
               prof_principal=d.get('prof_principal', ''))
    db.session.add(c); db.session.commit()
    return jsonify({'succes': True, 'id': c.id})

@app.route('/api/classes/<int:cid>', methods=['PUT'])
@login_required
@role_requis('directeur', 'censeur', 'secretaire')
def api_update_classe(cid):
    c = Classe.query.get_or_404(cid)
    d = request.get_json()
    c.nom = d.get('nom', c.nom).strip()
    c.niveau = d.get('niveau', c.niveau)
    c.serie = d.get('serie', c.serie)
    c.prof_principal = d.get('prof_principal', c.prof_principal)
    db.session.commit()
    return jsonify({'succes': True})

@app.route('/api/classes/<int:cid>', methods=['DELETE'])
@login_required
@role_requis('directeur')
def api_delete_classe(cid):
    c = Classe.query.get_or_404(cid)
    db.session.delete(c); db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API MATIÈRES
# ══════════════════════════════════════════

@app.route('/api/matieres', methods=['GET'])
@login_required
def api_matieres():
    matieres = Matiere.query.all()
    return jsonify([{'id': m.id, 'nom': m.nom, 'groupe': m.groupe or '—',
                     'coefficient': m.coefficient, 'enseignant': m.enseignant or '—'} for m in matieres])

@app.route('/api/matieres', methods=['POST'])
@login_required
@role_requis('directeur', 'censeur')
def api_add_matiere():
    d = request.get_json()
    m = Matiere(nom=d['nom'].strip(), groupe=d.get('groupe', ''),
                coefficient=float(d.get('coefficient', 1)), enseignant=d.get('enseignant', ''))
    db.session.add(m); db.session.commit()
    return jsonify({'succes': True, 'id': m.id})

@app.route('/api/matieres/<int:mid>', methods=['PUT'])
@login_required
@role_requis('directeur', 'censeur')
def api_update_matiere(mid):
    m = Matiere.query.get_or_404(mid)
    d = request.get_json()
    m.nom = d.get('nom', m.nom).strip()
    m.groupe = d.get('groupe', m.groupe)
    m.coefficient = float(d.get('coefficient', m.coefficient))
    m.enseignant = d.get('enseignant', m.enseignant)
    db.session.commit()
    return jsonify({'succes': True})

@app.route('/api/matieres/<int:mid>', methods=['DELETE'])
@login_required
@role_requis('directeur')
def api_delete_matiere(mid):
    m = Matiere.query.get_or_404(mid)
    db.session.delete(m); db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API NOTES
# ══════════════════════════════════════════

@app.route('/api/notes/<int:eleve_id>/<int:trimestre>', methods=['GET'])
@login_required
def api_notes(eleve_id, trimestre):
    notes = Note.query.filter_by(eleve_id=eleve_id, trimestre=trimestre).all()
    return jsonify([{'matiere_id': n.matiere_id, 'matiere': n.matiere.nom,
                     'coefficient': n.matiere.coefficient, 'note': n.note} for n in notes])

@app.route('/api/notes', methods=['POST'])
@login_required
@role_requis('directeur', 'censeur', 'enseignant')
def api_save_notes():
    d = request.get_json()
    eleve_id = d['eleve_id']
    trimestre = d['trimestre']
    for item in d.get('notes', []):
        mid = item['matiere_id']
        val = item.get('note')
        existing = Note.query.filter_by(eleve_id=eleve_id, matiere_id=mid, trimestre=trimestre).first()
        if val is not None and val != '':
            if existing:
                existing.note = float(val)
                existing.updated_at = datetime.utcnow()
            else:
                db.session.add(Note(eleve_id=eleve_id, matiere_id=mid, trimestre=trimestre, note=float(val)))
        elif existing:
            db.session.delete(existing)
    db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API ABSENCES
# ══════════════════════════════════════════

@app.route('/api/absences', methods=['GET'])
@login_required
def api_absences():
    classe_id = request.args.get('classe_id')
    eleve_id = request.args.get('eleve_id')
    statut = request.args.get('statut')
    query = Absence.query
    if eleve_id:
        query = query.filter_by(eleve_id=int(eleve_id))
    elif classe_id:
        ids = [e.id for e in Eleve.query.filter_by(classe_id=int(classe_id)).all()]
        query = query.filter(Absence.eleve_id.in_(ids))
    if statut:
        query = query.filter_by(statut=statut)
    absences = query.order_by(Absence.date.desc()).all()
    return jsonify([{
        'id': a.id, 'eleve': a.eleve.nom+' '+a.eleve.prenom,
        'eleve_id': a.eleve_id,
        'classe': a.eleve.classe.nom if a.eleve.classe else '—',
        'matiere': a.matiere.nom if a.matiere else '—',
        'date': a.date.strftime('%d/%m/%Y'),
        'heure_debut': a.heure_debut or '—',
        'heure_fin': a.heure_fin or '—',
        'statut': a.statut, 'motif': a.motif or '—'
    } for a in absences])

@app.route('/api/absences', methods=['POST'])
@login_required
@role_requis('directeur', 'censeur', 'enseignant')
def api_add_absence():
    d = request.get_json()
    date_abs = datetime.strptime(d['date'], '%Y-%m-%d').date()
    a = Absence(eleve_id=int(d['eleve_id']), date=date_abs,
                heure_debut=d.get('heure_debut'), heure_fin=d.get('heure_fin'),
                matiere_id=int(d['matiere_id']) if d.get('matiere_id') else None,
                statut=d.get('statut', 'injustifiee'), motif=d.get('motif', ''))
    db.session.add(a); db.session.commit()
    return jsonify({'succes': True, 'id': a.id})

@app.route('/api/absences/<int:aid>/justifier', methods=['PUT'])
@login_required
@role_requis('directeur', 'censeur')
def api_justifier_absence(aid):
    a = Absence.query.get_or_404(aid)
    d = request.get_json()
    a.statut = 'justifiee'
    a.motif = d.get('motif', a.motif)
    db.session.commit()
    return jsonify({'succes': True})

@app.route('/api/absences/<int:aid>', methods=['DELETE'])
@login_required
@role_requis('directeur', 'censeur')
def api_delete_absence(aid):
    a = Absence.query.get_or_404(aid)
    db.session.delete(a); db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API DEMANDES
# ══════════════════════════════════════════

@app.route('/api/demandes', methods=['GET'])
@login_required
def api_demandes():
    statut = request.args.get('statut')
    query = Demande.query
    if statut: query = query.filter_by(statut=statut)
    demandes = query.order_by(Demande.created_at.desc()).all()
    return jsonify([{
        'id': d.id, 'eleve': d.eleve.nom+' '+d.eleve.prenom,
        'classe': d.eleve.classe.nom if d.eleve.classe else '—',
        'type_demande': d.type_demande,
        'date_concernee': d.date_concernee.strftime('%d/%m/%Y') if d.date_concernee else '—',
        'motif': d.motif, 'statut': d.statut,
        'traite_par': d.traite_par or '—',
        'created_at': d.created_at.strftime('%d/%m/%Y %H:%M')
    } for d in demandes])

@app.route('/api/demandes', methods=['POST'])
@login_required
def api_add_demande():
    d = request.get_json()
    if current_user.role == 'eleve':
        eleve_id = current_user.eleve_id
    else:
        eleve_id = int(d['eleve_id'])
    date_dem = None
    if d.get('date_concernee'):
        try: date_dem = datetime.strptime(d['date_concernee'], '%Y-%m-%d').date()
        except: pass
    dem = Demande(eleve_id=eleve_id, type_demande=d['type_demande'],
                  date_concernee=date_dem, motif=d['motif'])
    db.session.add(dem); db.session.commit()
    return jsonify({'succes': True, 'id': dem.id})

@app.route('/api/demandes/<int:did>/traiter', methods=['PUT'])
@login_required
@role_requis('directeur', 'censeur')
def api_traiter_demande(did):
    dem = Demande.query.get_or_404(did)
    d = request.get_json()
    dem.statut = d['statut']
    dem.traite_par = current_user.nom
    dem.date_traitement = datetime.utcnow()
    if dem.statut == 'approuvee' and dem.type_demande == 'absence':
        a = Absence(eleve_id=dem.eleve_id, date=dem.date_concernee or date.today(),
                    statut='justifiee', motif=dem.motif)
        db.session.add(a)
    db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API BULLETINS
# ══════════════════════════════════════════

@app.route('/api/bulletin/<int:eleve_id>/<int:trimestre>', methods=['GET'])
@login_required
def api_bulletin(eleve_id, trimestre):
    if current_user.role == 'eleve' and current_user.eleve_id != eleve_id:
        return jsonify({'erreur': 'Non autorisé'}), 403
    e = Eleve.query.get_or_404(eleve_id)
    cl = e.classe
    moy = calc_moyenne(eleve_id, trimestre)
    mention, mention_cls = get_mention(moy)
    notes = Note.query.filter_by(eleve_id=eleve_id, trimestre=trimestre).all()
    rangs_cl = []
    if cl:
        for ev in cl.eleves:
            m = calc_moyenne(ev.id, trimestre)
            if m is not None: rangs_cl.append({'id': ev.id, 'moy': m})
    rangs_cl.sort(key=lambda x: x['moy'], reverse=True)
    rang = next((i+1 for i, r in enumerate(rangs_cl) if r['id'] == eleve_id), None)
    h_abs = calc_heures_abs(eleve_id)
    abs_ij = Absence.query.filter_by(eleve_id=eleve_id, statut='injustifiee').count()
    grps = {}
    for n in notes:
        g = n.matiere.groupe or 'Autres matières'
        if g not in grps: grps[g] = []
        grps[g].append({'matiere': n.matiere.nom, 'coefficient': n.matiere.coefficient,
                        'note': n.note, 'pts': round(n.note * n.matiere.coefficient, 2)})
    return jsonify({
        'eleve': {'nom': e.nom, 'prenom': e.prenom, 'sexe': 'Masculin' if e.sexe == 'M' else 'Féminin',
                  'matricule': e.matricule or '—',
                  'date_naissance': e.date_naissance.strftime('%d/%m/%Y') if e.date_naissance else '—',
                  'contact': e.contact_parent or '—'},
        'classe': {'nom': cl.nom if cl else '—', 'prof': cl.prof_principal if cl else '—'},
        'trimestre': trimestre, 'moy': moy, 'mention': mention, 'mention_cls': mention_cls,
        'rang': rang, 'total_cl': len(rangs_cl),
        'groupes': grps, 'h_abs': h_abs, 'abs_ij': abs_ij,
        'cfg': {'nom': get_config('nom', 'Lycée Malick Sy'), 'ville': get_config('ville', 'Thiès'),
                'annee': get_config('annee', '2024-2025'), 'proviseur': get_config('proviseur', '')}
    })

# ══════════════════════════════════════════
#  API PERSONNEL
# ══════════════════════════════════════════

@app.route('/api/personnel', methods=['GET'])
@login_required
@role_requis('directeur')
def api_personnel():
    users = Utilisateur.query.filter(Utilisateur.role != 'eleve').all()
    return jsonify([{'id': u.id, 'nom': u.nom, 'login': u.login, 'role': u.role, 'actif': u.actif} for u in users])

@app.route('/api/personnel', methods=['POST'])
@login_required
@role_requis('directeur')
def api_add_personnel():
    d = request.get_json()
    if Utilisateur.query.filter_by(login=d['login']).first():
        return jsonify({'erreur': 'Identifiant déjà utilisé'}), 400
    u = Utilisateur(nom=d['nom'].strip(), login=d['login'].strip(),
                    mot_de_passe=hash_password(d['password']), role=d['role'])
    db.session.add(u); db.session.commit()
    return jsonify({'succes': True})

@app.route('/api/personnel/<int:uid>', methods=['DELETE'])
@login_required
@role_requis('directeur')
def api_delete_personnel(uid):
    if uid == current_user.id:
        return jsonify({'erreur': 'Impossible de supprimer son propre compte'}), 400
    u = Utilisateur.query.get_or_404(uid)
    db.session.delete(u); db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  API CONFIG
# ══════════════════════════════════════════

@app.route('/api/config', methods=['GET'])
@login_required
def api_get_config():
    configs = Config.query.all()
    return jsonify({c.cle: c.valeur for c in configs})

@app.route('/api/config', methods=['POST'])
@login_required
@role_requis('directeur')
def api_save_config():
    d = request.get_json()
    for cle, valeur in d.items():
        c = Config.query.filter_by(cle=cle).first()
        if c: c.valeur = valeur
        else: db.session.add(Config(cle=cle, valeur=valeur))
    db.session.commit()
    return jsonify({'succes': True})

# ══════════════════════════════════════════
#  PORTAIL ÉLÈVE
# ══════════════════════════════════════════

@app.route('/mes-notes')
@login_required
def portal_notes():
    if current_user.role != 'eleve':
        return redirect(url_for('dashboard'))
    return render_template('portal.html', section='notes')

@app.route('/mes-absences')
@login_required
def portal_absences():
    if current_user.role != 'eleve':
        return redirect(url_for('dashboard'))
    return render_template('portal.html', section='absences')

@app.route('/mon-bulletin')
@login_required
def portal_bulletin():
    if current_user.role != 'eleve':
        return redirect(url_for('dashboard'))
    return render_template('portal.html', section='bulletin')

@app.route('/ma-demande')
@login_required
def portal_demande():
    if current_user.role != 'eleve':
        return redirect(url_for('dashboard'))
    return render_template('portal.html', section='demande')

# ══════════════════════════════════════════
#  PAGES STAFF
# ══════════════════════════════════════════

@app.route('/eleves')
@login_required
def page_eleves():
    return render_template('app.html', page='eleves')

@app.route('/classes')
@login_required
def page_classes():
    return render_template('app.html', page='classes')

@app.route('/matieres')
@login_required
def page_matieres():
    return render_template('app.html', page='matieres')

@app.route('/notes')
@login_required
def page_notes():
    return render_template('app.html', page='notes')

@app.route('/bulletins')
@login_required
def page_bulletins():
    return render_template('app.html', page='bulletins')

@app.route('/absences')
@login_required
def page_absences():
    return render_template('app.html', page='absences')

@app.route('/billets')
@login_required
def page_billets():
    return render_template('app.html', page='billets')

@app.route('/demandes')
@login_required
def page_demandes():
    return render_template('app.html', page='demandes')

@app.route('/personnel')
@login_required
def page_personnel():
    return render_template('app.html', page='personnel')

@app.route('/config')
@login_required
def page_config():
    return render_template('app.html', page='config')

# ══════════════════════════════════════════
#  INIT BASE DE DONNÉES
# ══════════════════════════════════════════

def init_db():
    with app.app_context():
        db.create_all()
        if not Utilisateur.query.filter_by(login='directeur').first():
            users = [
                ('Directeur Général', 'directeur', 'admin123', 'directeur'),
                ('Censeur Principal', 'censeur', 'censeur123', 'censeur'),
                ('Enseignant', 'enseignant', 'prof123', 'enseignant'),
                ('Secrétaire', 'secretaire', 'secr123', 'secretaire'),
            ]
            for nom, login, pwd, role in users:
                u = Utilisateur(nom=nom, login=login, mot_de_passe=hash_password(pwd), role=role)
                db.session.add(u)
            configs = [('nom', 'Lycée Malick Sy'), ('ville', 'Thiès'), ('annee', '2024-2025'), ('proviseur', '')]
            for cle, val in configs:
                db.session.add(Config(cle=cle, valeur=val))
            db.session.commit()
            print("✅ Base de données initialisée avec les comptes par défaut")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

# ══════════════════════════════════════════
#  INJECT USER JSON INTO ALL TEMPLATES
# ══════════════════════════════════════════
import json

@app.context_processor
def inject_user():
    if current_user.is_authenticated:
        return {'user_json': json.dumps({
            'id': current_user.id,
            'nom': current_user.nom,
            'role': current_user.role,
            'eleve_id': current_user.eleve_id
        })}
    return {'user_json': '{}'}
