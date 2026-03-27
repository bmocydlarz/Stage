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
    print(f"🤖 [ROBOT] Analyse du HTML réel (Sélecteurs Skiller)...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        # Injection des cookies
        cookies_json = os.getenv('JOBTEASER_COOKIES')
        if cookies_json:
            context.add_cookies(json.loads(cookies_json))

        page = context.new_page()
        
        try:
            for kw in keywords:
                search_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw.replace(' ', '+')}"
                print(f"🤖 [ROBOT] Recherche : {kw}")
                
                page.goto(search_url, wait_until="networkidle")
                time.sleep(5) # Laisser le temps au JS de Skiller d'injecter les offres

                # On cherche toutes les cartes d'offres (balises <a> principales)
                # Le sélecteur 'a.sk-Card_main__9_8dw' est le plus précis d'après ton HTML
                offers = page.locator('a[class*="sk-Card_main"]').all()
                
                if not offers:
                    # Backup : essayer de chercher par le titre si la classe sk-Card a changé
                    offers = page.locator('div[class*="JobAdCard"]').all()

                print(f"🎯 {len(offers)} offres détectées pour '{kw}'")

                for offer in offers:
                    try:
                        # Extraction du titre (h3)
                        title = offer.locator('h3[class*="JobAdCard_title"]').inner_text()
                        
                        # Extraction de l'entreprise (p avec data-testid)
                        company = offer.locator('[data-testid="jobad-card-company-name"]').inner_text()
                        
                        # Le lien est soit sur l'élément lui-même (si c'est le <a>), soit à l'intérieur
                        link = offer.get_attribute('href')
                        
                        if title and company and link:
                            full_link = f"https://ec-lyon.jobteaser.com{link}" if link.startswith('/') else link
                            results.append({
                                'title': title.strip(),
                                'company': company.strip(),
                                'location': 'Exclu JobTeaser (ENISE)',
                                'job_url': full_link,
                                'site': 'jobteaser'
                            })
                    except:
                        continue
                        
        except Exception as e:
            print(f"❌ Erreur durant le scraping : {e}")
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
