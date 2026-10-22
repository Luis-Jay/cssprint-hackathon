# Sellyo
> **Starting a small business in Manila should not take five trips to City Hall just to find out your documents are incomplete.**  
*A permit step by step progress, ordinance Q&A copilot, and document pre-checker for Manila small businesses.*

---

## The Story & Problem Statement

### Inspiration
If you have ever tried opening a small shop in Manila, like a cafe in Sampaloc, a carinderia near UST, or a retail store in Tondo, you know the struggle.

You take a day off work, wait in line for hours at City Hall, and finally reach Window 3 only to hear: *"Ay sir, kailangan niyo muna ng Barangay Clearance at Sanitary Permit bago ito."*

Then you head to the barangay hall, and find out you needed a DTI business name certificate first. It is the classic Filipino "pabalik-balik" problem. Most small business owners do not struggle because their idea is weak. They struggle because nobody tells them what papers they need and what exact order to get them in.

We are building Sellyo so first-time entrepreneurs can get their permits right the first time, without guessing and without paying fixers.

### Problem Statement
Propose a software solution to streamline business permit applications, eliminate reliance on illegal fixers, and guide entrepreneurs through transparent city compliance in the City of Manila.

- **Target User:** Solo founders, food stall operators, and first-time small business owners in the City of Manila.
- **Why it is broken today:**
  - **No clear sequence:** Government offices do not provide one unified checklist. If you apply for step 4 before step 2, the counter turns you away.
  - **Rules are buried in legal text:** Manila Ordinances (8119, 8331, 8341) and licensing guides are hundreds of pages of legal jargon that normal vendors do not have time to read.
  - **Wasted trips and lost income:** Bringing the wrong ID or an incomplete document means a wasted day in line and a delayed store opening.

### Expected Impact
- Over **99% of businesses in the Philippines are micro, small, and medium enterprises (MSMEs)**, but more than **60% operate informally** because the paperwork is overwhelming.
- Aims to cut physical office visits from **5 or more blind trips down to 1 or 2 prepared visits**.
- Aims to turn a confusing **3 to 4 week trial-and-error process into a clear checklist you can finish in days**, saving small owners money on wasted transport fares and lost daily sales.

---

## The Solution & Features

### Overview
Sellyo will be a guided assistant for Manila business permits. You describe your business in plain words, and Sellyo gives you a personalized step-by-step checklist based on Manila's actual laws, answers your questions, computes your fees, shows nearby offices on a map, and lets you check your document photos before you line up.

### Core Planned Features
- **Personalized Permit Roadmap:** Generates the exact sequence you need (DTI -> Barangay Clearance -> Line Bureau clearances like Fire and Sanitary -> Mayor's Permit at City Hall -> BIR) customized to your business type.
- **Government Office Map Locator (Google Maps API):** When a user selects their distrct, an interactive map shows the exact locations of nearby government offices they need to visit, such as the local Barangay Hall, Manila Health Department, BFP Fire Station, and City Hall.
- **City Tax and Fee Calculator:** Implements the Manila Revenue Code rate tables to compute your estimated municipal fees, Mayor's Permit charges, sanitary inspection fees, and fire inspection dues based on declared capital and floor area.
- **Ordinance Q&A Copilot:** Answers permit questions in plain English or Taglish (e.g., *"Kailangan ba ng health certificate kahit cashier lang ako?"*). It looks up actual Manila city ordinances and cites the source.
- **Document and ID Pre-Check:** Lets you upload a photo of your ID or clearance to check if it is readable, complete, and matches what the counter requires.
- **Printable Summary Card:** Once your permit steps are completed, Sellyo generates a clean, printable one-page summary card. It lists all your completed requirements, computed fees, and important reminders (such as bringing two photocopies per ID, bringing exact cash, and City Hall operating hours) so you can take it directly to the counter.
- **Progress Tracker:** Saves your progress so you can pick up where you left off.

---

## Tech Stack & Methodology

### Technologies We Plan to Use
- **Frontend:** Next.js, React, TypeScript, Tailwind CSS (built mobile-first so users can check it on their phones)
- **Backend & Server:** Python, FastAPI (hosted locally)
- **Database:** SQLite (local database)
- **Maps & Geolocation:** Google Maps API (interactive map for finding nearby government offices per zone)
- **AI & Vision:** Google Gemini API (Flash-Lite / Flash) for natural language reasoning and document photo checks
- **Knowledge Base (RAG):** Local FAISS vector search indexing Manila Ordinances (8119, 8331, 8341) and BPLS citizen charters

### Why AI is Necessary
- **Every business has different requirements:** A food stall needs sanitary permits and health cards. A retail shop needs different zoning and safety clearances. AI translates everyday descriptions into the exact legal rules that apply instead of forcing users through complicated tables.
- **Ordinances are long and hard to navigate:** Instead of guessing, RAG searches Manila's actual ordinances and gives factual answers with citations.
- **Checking phone photos of documents:** Simple code cannot tell if a photo of a Barangay Clearance is blurry or missing an official seal. Vision models can inspect and flag these issues before counter submission.

---

## Scope & Limitations

### What we will build during the hackathon
- **Business Profile Input:** You describe your business, and the app identifies what type of business it is and where it is located.
- **5-Stage Permit Roadmap:** A step-by-step checklist showing which permits you need first, second, and last in Manila.
- **Nearby Government Office Map:** A dropdown for Manila zones and districts (e.g., Zone 30, Sampaloc) that pins nearby government offices on Google Maps.
- **City Tax and Fee Computation:** Implements official Manila Revenue Code formulas to compute estimated city taxes, regulatory fees, and fire inspection charges based on declared capital and space.
- **Manila Ordinance Q&A:** An AI chat assistant that answers permit questions using actual city ordinances as reference.
- **Document Photo Check:** You upload a photo of your ID or clearance, and the app checks if the text is readable and if it is the right document type.
- **Printable Summary Card:** Generates a one-page printable cheat sheet with key reminders, computed fees, and document checklist for your counter visit once requirements are complete.
- **Local Server & Storage:** The application runs with the PC as the local server and stores all progress in a local SQLite database.

### What is out of scope (What it cannot do)
- **It does not submit forms for you:** You still have to bring or submit your documents yourself. We do not have official access to the GoManila city database.
- **It only covers the City of Manila:** Other cities like Quezon City, Makati, or Pasig have different local rules and are not supported yet.
- **It does not verify legal identity:** The app only checks if your uploaded document looks readable and complete. It does not verify government records.