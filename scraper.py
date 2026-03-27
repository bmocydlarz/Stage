import pandas as pd
from jobspy import scrape_jobs
import datetime

def generate_html(df):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mes Stages Méca 🛠️</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100 p-5">
        <div class="max-w-2xl mx-auto">
            <h1 class="text-3xl font-bold text-blue-800 mb-2">Ma Veille Stage 🎯</h1>
            <p class="text-gray-600 mb-6">Mis à jour le : {datetime.date.today()}</p>
            <div class="space-y-4">
    """
    
    for _, row in df.iterrows():
        html_content += f"""
        <div class="bg-white p-4 rounded-lg shadow-md border-l-4 border-blue-500">
            <h2 class="text-xl font-semibold text-gray-800">{row['title']}</h2>
            <p class="text-blue-600 font-medium">{row['company']} • {row['location']}</p>
            <p class="text-sm text-gray-500 mt-2">Source : {row['site']}</p>
            <a href="{row['job_url']}" target="_blank" 
               class="inline-block mt-3 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition">
               Voir l'offre
            </a>
        </div>
        """
    
    html_content += "</div></div></body></html>"
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

# Lancement du scraping
jobs = scrape_jobs(
    site_name=["indeed", "linkedin"],
    search_term="Assistant Ingénieur Génie Mécanique",
    location="France",
    results_wanted=15,
    hours_old=72,
    country_indeed='france'
)

# On filtre un peu (mots-clés méca/septembre)
if not jobs.empty:
    generate_html(jobs)
