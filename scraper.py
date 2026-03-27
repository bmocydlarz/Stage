import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
import os, json

# Config Firebase via Secret GitHub
if os.getenv('FIREBASE_SERVICE_ACCOUNT'):
    cred = credentials.Certificate(json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT')))
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    USERS = {
        "baptiste.mocydlarz@enise.fr": {"villes": ["Saint-Étienne, France", "Quesnoy-sur-Deûle, France"], "dist": 15},
        "mourad.ismaila@enise.fr": {"villes": ["Lyon, France", "Saint-Étienne, France", "Bordeaux, France"], "dist": 3}
    }

    for email, prefs in USERS.items():
        results = []
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
                if not jobs.empty: results.append(jobs)
            except: continue

        if results:
            df = pd.concat(results).drop_duplicates(subset=['job_url'])
            db.collection('jobs').document(email).set({'offers': df.to_dict(orient='records')})
            print(f"✅ Mis à jour pour {email}")
