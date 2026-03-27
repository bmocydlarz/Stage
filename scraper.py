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
                print(f"---")
                print(f"🤖 [ROBOT] Recherche : {kw}")
                
                try:
                    # 1. On y va, mais on n'attend PAS que tout le réseau soit calme
                    page.goto(search_url, wait_until="commit") 
                    
                    # 2. On attend spécifiquement qu'UNE carte d'offre soit visible (max 20s)
                    # C'est BEAUCOUP plus fiable que networkidle
                    print("🤖 [ROBOT] Attente de l'apparition des offres...")
                    page.wait_for_selector('a[class*="sk-Card_main"]', timeout=20000)
                    
                    # Petit sleep pour que le texte des titres finisse de charger
                    time.sleep(2) 

                    # 3. On récupère les offres
                    offers = page.locator('a[class*="sk-Card_main"]').all()
                    print(f"🎯 {len(offers)} offres détectées pour '{kw}'")

                    for offer in offers:
                        try:
                            # Sélecteur précis basé sur ton HTML
                            title_el = offer.locator('h3[class*="JobAdCard_title"]')
                            company_el = offer.locator('[data-testid="jobad-card-company-name"]')
                            
                            title = title_el.inner_text()
                            company = company_el.inner_text()
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
                    print(f"⚠️ Pas d'offres trouvées ou page trop lente pour '{kw}'")
                    # On continue au mot-clé suivant au lieu de tout couper
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
