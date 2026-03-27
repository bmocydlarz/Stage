import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time, random

# --- 1. INITIALISATION FIREBASE ---
def init_firebase():
    if not firebase_admin._apps:
        service_account_info = json.loads(os.getenv('FIREBASE_SERVICE_ACCOUNT'))
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# --- 2. FONCTION SCRAPING JOBTEASER ---
def scrape_jobteaser(email, password, keywords):
    results = []
    print(f"🤖 [ROBOT] Tentative de bypass via Cookies de session...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # On utilise un contexte propre
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        # Injection des cookies exportés
        try:
            cookies_json = os.getenv('JOBTEASER_COOKIES')
            if cookies_json:
                cookies = json.loads(cookies_json)
                context.add_cookies(cookies)
                print("✅ Badge d'accès (Cookies) injecté.")
        except Exception as e:
            print(f"❌ Erreur format Cookies : {e}")

        page = context.new_page()
        
        try:
            for kw in keywords:
                # On utilise l'URL de recherche du portail EC-LYON
                search_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw.replace(' ', '+')}"
                print(f"---")
                print(f"🤖 [ROBOT] Navigation directe : {search_url}")
                
                # On charge la page
                page.goto(search_url, wait_until="domcontentloaded")
                
                # Pause pour laisser le contenu dynamique arriver
                time.sleep(7) 
                
                print(f"🤖 [ROBOT] Titre de la page : {page.title()}")

                # On vérifie si les offres sont là
                if page.locator("article").count() > 0:
                    offers = page.locator("article").all()
                    print(f"🎯 TROUVÉ : {len(offers)} offres pour '{kw}'")
                    
                    for offer in offers:
                        try:
                            title = offer.locator('h2, h3').first.inner_text()
                            company = offer.locator('p').first.inner_text()
                            link = offer.locator('a').first.get_attribute('href')
                            
                            if title and company and link:
                                full_link = f"https://ec-lyon.jobteaser.com{link}" if link.startswith('/') else link
                                results.append({
                                    'title': title.strip(),
                                    'company': company.strip(),
                                    'location': 'Exclu JobTeaser (ENISE/Centrale)',
                                    'job_url': full_link,
                                    'site': 'jobteaser'
                                })
                        except: continue
                else:
                    print(f"🤖 [ROBOT] ⚠️ Aucune offre visible. (Cloudflare bloque peut-être encore ou cookies expirés)")

        except Exception as e:
            print(f"🤖 [ROBOT] ❌ Erreur : {e}")
        finally:
            browser.close()
            
    return results

# --- 3. EXECUTION PRINCIPALE ---
if __name__ == "__main__":
    db = init_firebase()
    
    USERS = {
        "baptiste.mocydlarz@etu-enise.ec-lyon.fr": {"villes": ["Saint-Étienne", "Lille"], "dist": 30}
    }

    MOTS_CLES = ["Stage Génie Mécanique", "Stage Conception CAO", "Stage Industrialisation", "Stage R&D"]
    JT_PASS = os.getenv('JOBTEASER_PASS')

    for email, prefs in USERS.items():
        all_results = []

        # A. JobSpy (LinkedIn/Indeed)
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
                    if not jobs.empty: all_results.append(jobs)
                except: continue

        # B. JobTeaser (Furtif)
        if JT_PASS:
            jt_data = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_data: all_results.append(pd.DataFrame(jt_data))

        # C. Firebase
        if all_results:
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            final_df = final_df.astype(str)
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres stockées.")
