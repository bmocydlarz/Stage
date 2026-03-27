import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
import os, json

# Initialisation Firebase
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
            "dist": 5
        },
        "trystan.colichet@enise.fr": {
            "villes": ["Saint-Étienne, France", "Bourges, France"],
            "dist": 30
        },
        "leonard.dupuis@enise.fr": {
            "villes": ["Saint-Étienne, France", "Saint-Malo, France"],
            "dist": 10
        }
    }

    MOTS_CLES = ["Stage Génie Mécanique", "Assistant Ingénieur Mécanique", "Stage Conception Mécanique"]

    print("🚀 Démarrage du robot ENISE STAGES...")

    for email, prefs in USERS.items():
        print(f"🔎 Scraping pour : {email}")
        all_results = []
        
        for ville in prefs["villes"]:
            for poste in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=poste,
                        location=ville,
                        distance=prefs["dist"],
                        results_wanted=15,
                        hours_old=336, # 14 jours pour plus d'offres
                        country_indeed='france'
                    )
                    if not jobs.empty:
                        all_results.append(jobs)
                except:
                    continue

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            
            # Correction cruciale pour les erreurs Firestore (vu dans les logs)
            final_df = final_df.astype(str) 

            # Envoi dans un document portant l'e-mail de l'utilisateur
            db.collection('jobs').document(email.lower().strip()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Terminé pour {email}")
