import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time

# --- 1. INITIALISATION FIREBASE ---
def init_firebase():
    if not firebase_admin._apps:
        # Récupération du secret depuis GitHub Actions
        service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🔑 Connexion JobTeaser pour {email}...")
    
    with sync_playwright() as p:
        # On lance le navigateur
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()
        
        try:
            # URL de connexion Centrale Lyon / ENISE
            login_url = "https://connect.jobteaser.com/?client_id=e500827d-07fc-4766-97b4-4f960a2835e7&entity_name=Ecole+Centrale+Lyon&organization_domain=ec-lyon&redirect_uri=https%3A%2F%2Fwww.jobteaser.com%2Fusers%2Fauth%2Fconnect%2Fcallback&response_type=code&ui_locales=fr"
            page.goto(login_url, wait_until="networkidle")
            
            # Remplissage du formulaire
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            page.click('button[type="submit"]')
            
            # Attente de la redirection vers les offres
            page.wait_for_url("**/job-offers**", timeout=60000)
            print("✅ Connexion JobTeaser réussie !")

            for kw in keywords:
                search_url = f"https://www.jobteaser.com/fr/job-offers?query={kw.replace(' ', '+')}"
                page.goto(search_url, wait_until="networkidle")
                time.sleep(2) # Laisse le temps au JS de charger les cartes

                offers = page.locator('article').all()
                for offer in offers:
                    try:
                        title = offer.locator('h2').inner_text()
                        company = offer.locator('p').first.inner_text()
                        link = offer.locator('a').first.get_attribute('href')
                        full_link = f"https://www.jobteaser.com{link}" if link.startswith('/') else link
                        
                        results.append({
                            'title': title,
                            'company': company,
                            'location': 'JobTeaser (Centrale/ENISE)',
                            'job_url': full_link,
                            'site': 'jobteaser'
                        })
                    except: continue
        except Exception as e:
            print(f"⚠️ Erreur JobTeaser : {e}")
        finally:
            browser.close()
    return results

# --- 3. EXECUTION PRINCIPALE ---
if __name__ == "__main__":
    db = init_firebase()
    
    # Configuration des utilisateurs
    # NOTE: L'email ici doit être celui utilisé pour JobTeaser
    USERS = {
        "baptiste.mocydlarz@etu-enise.ec-lyon.fr": {"villes": ["Saint-Étienne", "Lille"], "dist": 30}
    }

    MOTS_CLES = ["Stage Génie Mécanique", "Stage Conception CAO", "Stage Industrialisation", "Stage R&D"]
    JT_PASS = os.getenv('JOBTEASER_PASS')

    for email, prefs in USERS.items():
        all_results = []

        # A. Scraping JobSpy (LinkedIn/Indeed)
        print(f"🔎 Scraping Public pour {email}...")
        for loc in prefs["villes"]:
            for kw in MOTS_CLES:
                try:
                    jobs = scrape_jobs(
                        site_name=["linkedin", "indeed"],
                        search_term=kw,
                        location=f"{loc}, France",
                        distance=prefs["dist"],
                        results_wanted=15,
                        hours_old=336,
                        country_indeed='france'
                    )
                    if not jobs.empty:
                        all_results.append(jobs)
                except: continue

        # B. Scraping JobTeaser
        if JT_PASS:
            jt_jobs = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_jobs:
                all_results.append(pd.DataFrame(jt_jobs))

        # C. Envoi vers Firebase
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            # Nettoyage pour Firebase
            final_df = final_df.astype(str)
            
            # On utilise l'email en minuscule comme ID de document
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres stockées pour {email}")
