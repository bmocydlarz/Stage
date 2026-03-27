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
    print(f"🤖 [ROBOT] Démarrage du module furtif JobTeaser...")
    
    with sync_playwright() as p:
        # Lancement avec masquage des flags d'automatisation
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox'
        ])
        
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        # Script pour supprimer la trace "webdriver" détectée par Cloudflare
        page = context.new_page()
        page.add_init_script("delete navigator.__proto__.webdriver")
        
        try:
            # 1. Connexion via le portail école
            print(f"🤖 [ROBOT] Accès à ec-lyon.jobteaser.com...")
            page.goto("https://ec-lyon.jobteaser.com/", wait_until="networkidle")
            time.sleep(random.uniform(2, 4))

            # Gestion des cookies pour débloquer le formulaire
            try:
                page.click('button:has-text("Accepter"), button:has-text("Tout accepter")', timeout=5000)
                print("🤖 [ROBOT] Cookies acceptés.")
            except: pass

            # 2. Saisie humaine
            print(f"🤖 [ROBOT] Saisie des identifiants...")
            page.fill('input[type="email"]', email)
            time.sleep(random.uniform(0.5, 1.5))
            page.fill('input[type="password"]', password)
            time.sleep(random.uniform(0.5, 1.0))
            page.keyboard.press("Enter")
            
            # Attente de la redirection (Dashboard)
            page.wait_for_url("**/dashboard**", timeout=45000)
            print(f"🤖 [ROBOT] ✅ Connexion réussie ! (URL: {page.url})")
            time.sleep(3)

            # 3. Boucle de recherche
            for kw in keywords:
                print(f"---")
                print(f"🤖 [ROBOT] Recherche de : '{kw}'")
                
                # Navigation vers la page d'offres
                page.goto("https://ec-lyon.jobteaser.com/fr/job-offers", wait_until="domcontentloaded")
                time.sleep(random.uniform(4, 6)) # Pause pour laisser Cloudflare tranquille

                # Vérification anti-blocage
                if "Just a moment" in page.title():
                    print("🤖 [ROBOT] 🛡️ Cloudflare détecté. Tentative de passage en force...")
                    time.sleep(10)

                try:
                    # On tape le mot-clé dans la barre de recherche
                    search_input = page.locator('input[type="search"], #query').first
                    search_input.click()
                    page.keyboard.type(kw, delay=random.randint(100, 200)) # Tape comme un humain
                    page.keyboard.press("Enter")
                    
                    # Attente des résultats
                    page.wait_for_selector('article', timeout=20000)
                    time.sleep(3)
                    
                    offers = page.locator('article').all()
                    print(f"🤖 [ROBOT] ✨ Succès : {len(offers)} offres trouvées.")
                    
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
                                    'location': 'Exclu JobTeaser (ENISE)',
                                    'job_url': full_link,
                                    'site': 'jobteaser'
                                })
                        except: continue
                except Exception as e:
                    print(f"🤖 [ROBOT] ❌ Échec sur '{kw}' (Titre: {page.title()})")
                    continue

        except Exception as e:
            print(f"🤖 [ROBOT] ❌ ERREUR : {e}")
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
