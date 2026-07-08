from bs4 import BeautifulSoup
with open('cart_seisan_debug2.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
inputs = soup.find_all(['input', 'select', 'textarea'])
for tag in inputs:
    name = tag.get('name')
    tid = tag.get('id')
    ttype = tag.get('type')
    if ttype != 'hidden':
        print(f"Tag: {tag.name}, Type: {ttype}, ID: {tid}, Name: {name}")
