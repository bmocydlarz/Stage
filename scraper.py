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

    USERS = {
        "baptiste.mocydlarz@enise.fr": {
            "villes": ["Saint-Étienne", "Quesnoy-sur-Deûle", "Lille"],
            "dist": 20 
        },
        "mourad.ismaila@enise.fr": {
            "villes": ["Lyon", "Saint-Étienne", "Bordeaux"],
            "dist": 10
        }
    }

    for email, prefs in USERS.items():
        print(f"🔎 Scraping pour : {email}")
        all_results = []
        
        for loc in prefs["villes"]:
            try:
                jobs = scrape_jobs(
                    site_name=["linkedin", "indeed"],
                    search_term="Stage Génie Mécanique",
                    location=f"{loc}, France",
                    distance=prefs["dist"],
                    results_wanted=20,
                    hours_old=168,
                    country_indeed='france'
                )
                if not jobs.empty:
                    # Filtre strict : on ne garde que si la ville est dans ta liste perso
                    mask = jobs['location'].str.contains('|'.join(prefs["villes"]), case=False, na=False)
                    all_results.append(jobs[mask])
            except:
                continue

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            # Conversion en texte pour éviter les erreurs de date Firestore
            final_df = final_df.astype(str)

            # Enregistrement dans le document spécifique à l'utilisateur
            db.collection('jobs').document(email).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ Succès pour {email}")
