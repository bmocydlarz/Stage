import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
import os, json

# Initialisation Firebase via GitHub Secret
if os.getenv('FIREBASE_SERVICE_ACCOUNT'):
    service_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(service_info)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # CONFIGURATION DES UTILISATEURS
    USERS = {
        "baptiste.mocydlarz@enise.fr": {
            "villes": ["Saint-Étienne, France", "Quesnoy-sur-Deûle, France"],
            "dist": 15
        },
        "mourad.ismaila@enise.fr": {
            "villes": ["Lyon, France", "Saint-Étienne, France", "Bordeaux, France"],
            "dist": 3
        },
        "trystan.colichet@enise.fr": {
            "villes": ["Saint-Étienne, France", "Bourges, France"],
            "dist": 30
        },
        "leonard.dupuis@enise.fr": {
            "villes": ["Saint-Étienne, France", "Saint-Malo, France"],
            "dist": 9
        }
    }

    print("🚀 Démarrage du robot ENISE STAGES...")

    for email, prefs in USERS.items():
        print(f"🔎 Scraping pour : {email}")
        all_results = []
        
        for ville in prefs["villes"]:
            try:
                jobs = scrape_jobs(
                    site_name=["linkedin", "indeed"],
                    search_term="Stage Génie Mécanique",
                    location=ville,
                    distance=prefs["dist"],
                    results_wanted=15,
                    hours_old=168,
                    country_indeed='france'
                )
                if not jobs.empty:
                    all_results.append(jobs)
            except Exception as e:
                print(f"❌ Erreur sur {ville} : {e}")

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            
            # --- CORRECTION ICI : Conversion des dates en texte pour Firestore ---
            # On transforme tout ce qui ressemble à une date en format texte "YYYY-MM-DD"
            for col in final_df.columns:
                if final_df[col].dtype == 'object' or 'date' in col:
                    final_df[col] = final_df[col].astype(str)

            # Envoi vers Firebase
            db.collection('jobs').document(email).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Terminé pour {email} : {len(final_df)} offres.")
        else:
            print(f"⚠️ Aucune offre trouvée pour {email}")
