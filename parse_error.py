from bs4 import BeautifulSoup
with open('cart_seisan_final.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
err = soup.find(id='error')
if err:
    print("ERROR MSG:", err.text.strip())
errs = soup.find_all(class_='form-error-message')
for e in errs:
    print("FORM ERROR:", e.text.strip())
