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
            "search_loc": "Saint-Étienne, France",
            "dist": 20 
        },
        "mourad.ismaila@enise.fr": {
            "villes": ["Lyon", "Saint-Étienne", "Bordeaux"],
            "search_loc": "Lyon, France",
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
                    # FILTRE DE SÉCURITÉ : On ne garde que si la ville est dans ta liste
                    jobs = jobs[jobs['location'].str.contains('|'.join(prefs["villes"]), case=False, na=False)]
                    all_results.append(jobs)
            except:
                continue

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            [span_2](start_span)final_df = final_df.astype(str) # Évite l'erreur de date[span_2](end_span)

            # On enregistre dans le document spécifique à l'utilisateur
            db.collection('jobs').document(email).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
