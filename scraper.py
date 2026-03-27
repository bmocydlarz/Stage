import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
import os, json

if os.getenv('FIREBASE_SERVICE_ACCOUNT'):
    service_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
    cred = credentials.Certificate(service_info)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()

    # CONFIGURATION DES 4 UTILISATEURS
    USERS = {
        "baptiste.mocydlarz@enise.fr": {"villes": ["Saint-Étienne", "Quesnoy-sur-Deûle", "Lille"], "dist": 20},
        "mourad.ismaila@enise.fr": {"villes": ["Lyon", "Saint-Étienne", "Bordeaux"], "dist": 15},
        "trystan.colichet@enise.fr": {"villes": ["Saint-Étienne", "Bourges"], "dist": 30},
        "leonard.dupuis@enise.fr": {"villes": ["Saint-Étienne", "Saint-Malo"], "dist": 15}
    }

    # Élargissement des termes pour avoir plus d'offres
    MOTS_CLES = ["Stage Génie Mécanique", 
    "Assistant Ingénieur Mécanique", 
    "Stage Conception CAO", 
    "Stage Industrialisation",
    "Stage R&D Mécanique"]

    print("🚀 Robot ENISE STAGES en route...")

    for email, prefs in USERS.items():
        print(f"🔎 Recherche pour : {email}")
        all_results = []
        for loc in prefs["villes"]:
            for kw in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=kw,
                        location=f"{loc}, France",
                        distance=prefs["dist"],
                        results_wanted=30,
                        hours_old=336, # On regarde sur 14 jours
                        country_indeed='france'
                    )
                    if not jobs.empty:
                        # Filtrage strict pour éviter les erreurs de ville
                        mask = jobs['location'].str.contains('|'.join(prefs["villes"]), case=False, na=False)
                        all_results.append(jobs[mask])
                except: continue

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            # Conversion en texte pour éviter les plantages Firebase (vu dans les logs)
            final_df = final_df.astype(str) 

            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Document mis à jour pour {email}")
