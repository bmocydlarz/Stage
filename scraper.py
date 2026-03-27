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
        "baptiste.mocydlarz@enise.fr": {"villes": ["Saint-Étienne, France", "Quesnoy-sur-Deûle, France"], "dist": 15},
        "mourad.ismaila@enise.fr": {"villes": ["Lyon, France", "Saint-Étienne, France", "Bordeaux, France"], "dist": 5},
        "trystan.colichet@enise.fr": {"villes": ["Saint-Étienne, France", "Bourges, France"], "dist": 30},
        "leonard.dupuis@enise.fr": {"villes": ["Saint-Étienne, France", "Saint-Malo, France"], "dist": 10}
    }

    # Liste de mots-clés élargie pour trouver plus de stages
    MOTS_CLES = ["Stage Génie Mécanique", "Assistant Ingénieur Mécanique", "Stage Conception Mécanique", "Stage Maintenance"]

    for email, prefs in USERS.items():
        all_results = []
        for ville in prefs["villes"]:
            for poste in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=poste,
                        location=ville,
                        distance=prefs["dist"],
                        results_wanted=20, # On demande plus de résultats
                        hours_old=336,    # On regarde sur 14 jours au lieu de 7 pour avoir plus de choix
                        country_indeed='france'
                    )
                    if not jobs.empty:
                        all_results.append(jobs)
                except:
                    continue

        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            
            # [span_11](start_span)[span_12](start_span)Conversion en string pour éviter les erreurs Firestore vues dans les logs[span_11](end_span)[span_12](end_span)
            final_df = final_df.astype(str) 

            db.collection('jobs').document(email).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✅ {len(final_df)} offres pour {email}")
