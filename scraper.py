import pandas as pd
from jobspy import scrape_jobs
import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright
import os, json, time

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
    print(f"🤖 [ROBOT] Connexion directe via le portail école : ec-lyon.jobteaser.com")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()
        
        try:
            # 1. Accès au portail
            print(f"🤖 [ROBOT] ÉTAPE 1 : Chargement de https://ec-lyon.jobteaser.com/ ...")
            page.goto("https://ec-lyon.jobteaser.com/", wait_until="domcontentloaded")
            time.sleep(2)
            print(f"🤖 [ROBOT] URL actuelle après chargement : {page.url}")
            print(f"🤖 [ROBOT] Titre de la page : '{page.title()}'")
            
            # 2. Saisie des identifiants
            print(f"🤖 [ROBOT] ÉTAPE 2 : Saisie des identifiants pour {email}...")
            page.fill('input[type="email"]', email)
            page.fill('input[type="password"]', password)
            page.keyboard.press("Enter")
            
            # 3. Attente de la connexion
            print(f"🤖 [ROBOT] ÉTAPE 3 : Attente de la redirection post-connexion...")
            page.wait_for_url("https://ec-lyon.jobteaser.com/**", timeout=30000)
            print(f"🤖 [ROBOT] ✅ CONNECTÉ ! URL de destination : {page.url}")

            # 4. Boucle de recherche
            for kw in keywords:
                kw_encoded = kw.replace(' ', '+')
                search_url = f"https://ec-lyon.jobteaser.com/fr/job-offers?query={kw_encoded}&q={kw_encoded}"
                
                print(f"---")
                print(f"🤖 [ROBOT] RECHERCHE EN COURS : '{kw}'")
                print(f"🤖 [ROBOT] Je me rends sur : {search_url}")
                
                page.goto(search_url)
                # On attend que la page soit stable
                page.wait_for_load_state("domcontentloaded")
                print(f"🤖 [ROBOT] Page chargée. URL confirmée : {page.url}")
                
                try:
                    # On attend que les cartes d'offres apparaissent
                    print(f"🤖 [ROBOT] J'attends l'apparition des balises <article>...")
                    page.wait_for_selector('article', timeout=15000)
                    time.sleep(3) 
                    
                    offers = page.locator('article').all()
                    count_kw = len(offers)
                    print(f"🤖 [ROBOT] 🎯 TROUVÉ : {count_kw} offres détectées pour '{kw}'.")
                    
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
                except Exception as e:
                    print(f"🤖 [ROBOT] ❌ ÉCHEC : Aucune offre trouvée ou timeout sur cette page.")
                    print(f"🤖 [ROBOT] Diagnostic : Je suis sur '{page.url}' et le titre est '{page.title()}'")

        except Exception as e:
            print(f"🤖 [ROBOT] ❌ ERREUR FATALE : {e}")
            print(f"🤖 [ROBOT] Position finale du robot : {page.url}")
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

        # A. Scraping Public (LinkedIn/Indeed)
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

        # B. Scraping JobTeaser (Portail École)
        if JT_PASS:
            jt_jobs = scrape_jobteaser(email, JT_PASS, MOTS_CLES)
            if jt_jobs:
                all_results.append(pd.DataFrame(jt_jobs))

        # C. Fusion et Envoi vers Firebase
        if all_results:
            # Fusion de tous les DataFrames (Public + JobTeaser)
            final_df = pd.concat(all_results).drop_duplicates(subset=['job_url'])
            final_df = final_df.astype(str)
            
            db.collection('jobs').document(email.lower()).set({
                'offers': final_df.to_dict(orient='records'),
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            print(f"✨ Terminé ! {len(final_df)} offres au total stockées pour {email}")
