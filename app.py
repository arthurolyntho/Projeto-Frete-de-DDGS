
import os, re, time, unicodedata
import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = "https://consulta.maisfrete.com.br/exe_consulta_frete_minimo.php"

st.set_page_config(page_title="FortiPro | Preço Posto", page_icon="🚚", layout="wide")

def br_money(v):
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def br_to_float(txt):
    if not txt:
        return None
    txt = txt.replace("R$", "").strip().replace(".", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    return float(m.group()) if m else None

def normalizar(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower().strip()

def get_driver():
    opts = Options()
    for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-gpu","--window-size=1440,1200"]:
        opts.add_argument(arg)
    for p in ["/usr/bin/chromium","/usr/bin/chromium-browser"]:
        if os.path.exists(p):
            opts.binary_location = p
            break
    for p in ["/usr/bin/chromedriver","/usr/lib/chromium/chromedriver"]:
        if os.path.exists(p):
            return webdriver.Chrome(service=Service(p), options=opts)
    return webdriver.Chrome(options=opts)

def selecionar_cidade(driver, input_id, hidden_id, busca, uf):
    js = r"""
    const done=arguments[arguments.length-1], inputId=arguments[0],
          hiddenId=arguments[1], busca=arguments[2], uf=arguments[3];
    const url="/lib/jaguar/AjaxIframe.php?c=Cidade&a=obterCidadesAutoComplete&p%5BdsItem%5D="+encodeURIComponent(busca);
    fetch(url,{credentials:"same-origin",headers:{"X-Requested-With":"XMLHttpRequest"}})
      .then(r=>r.json()).then(d=>{
        const x=d.find(i=>(i.description||"").endsWith("/ "+uf));
        if(!x){done({ok:false,dados:d});return;}
        document.getElementById(inputId).value=x.description;
        document.getElementById(hiddenId).value=x.value;
        done({ok:true,cidade:x});
      }).catch(e=>done({ok:false,erro:String(e)}));
    """
    return driver.execute_async_script(js, input_id, hidden_id, busca, uf)

def clicar(driver, texto):
    return driver.execute_script("""
      const t=arguments[0].toLowerCase();
      const e=[...document.querySelectorAll("button,input[type=button],input[type=submit]")]
        .find(x=>((x.innerText||x.value||"").trim().toLowerCase()).includes(t));
      if(!e) return false; e.click(); return true;
    """, texto)

def cotar(origem, uf_o, destino, uf_d, eixos, peso, margem):
    d = get_driver()
    try:
        d.get(URL)
        w = WebDriverWait(d, 30)
        w.until(EC.presence_of_element_located((By.ID,"input-0")))

        ro = selecionar_cidade(d,"input-0","f_cd_cidade_origem",normalizar(origem),uf_o.upper())
        rd = selecionar_cidade(d,"input-1","f_cd_cidade_destino",normalizar(destino),uf_d.upper())
        if not ro.get("ok"): raise RuntimeError("Origem não encontrada")
        if not rd.get("ok"): raise RuntimeError("Destino não encontrado")

        if not clicar(d,"roteirizar"): raise RuntimeError("Botão Roteirizar não encontrado")
        w.until(lambda x: (x.find_element(By.ID,"qtKmRodado").get_attribute("value") or "").strip())
        km = d.find_element(By.ID,"qtKmRodado").get_attribute("value").strip()

        d.execute_script("""
          const v=arguments[0];
          Object.entries(v).forEach(([id,val])=>{
            const e=document.getElementById(id);
            if(e){e.value=val;e.dispatchEvent(new Event("input",{bubbles:true}));
            e.dispatchEvent(new Event("change",{bubbles:true}));}
          });
        """,{
          "qtEixos":str(eixos),
          "prMargemTransportadora":str(margem).replace(".",","),
          "vlPesoTonelada":f"{float(peso):.2f}".replace(".",",")
        })

        if not clicar(d,"calcular"): raise RuntimeError("Botão Calcular não encontrado")
        w.until(lambda x: x.execute_script("""
          return [...document.querySelectorAll("tr")].some(l=>(l.innerText||"").includes("Granel Sólido"));
        """))
        time.sleep(1)

        vals = d.execute_script("""
          const l=[...document.querySelectorAll("tr")].find(x=>(x.innerText||"").includes("Granel Sólido"));
          return l ? [...l.querySelectorAll("td,th")].map(x=>(x.innerText||"").trim()).filter(Boolean) : null;
        """)
        if not vals or len(vals)<7: raise RuntimeError(f"Linha inválida: {vals}")

        return {
          "origem":ro["cidade"]["description"], "destino":rd["cidade"]["description"],
          "km":br_to_float(km), "frete_min":br_to_float(vals[3]),
          "frete_min_t":br_to_float(vals[4]), "frete_emp":br_to_float(vals[5]),
          "frete_emp_t":br_to_float(vals[6])
        }
    finally:
        d.quit()

st.title("FortiPro | Formação de preço")
tab1,tab2,tab3 = st.tabs(["V1 • Produto","V2 • Logística","V3 • Fiscal"])

with tab1:
    c1,c2=st.columns(2)
    with c1:
        forti=st.number_input("FOB FortiPro (R$/t)",value=1445.0,step=10.0)
        pb_f=st.number_input("PB FortiPro (%)",value=35.0,step=0.5)
    with c2:
        soja=st.number_input("FOB Farelo (R$/t)",value=2130.0,step=10.0)
        pb_s=st.number_input("PB Farelo (%)",value=46.0,step=0.5)
    frete=st.session_state.get("frete_emp_t",0.0)
    posto=forti+frete
    eco=soja-posto
    pct=(eco/soja*100) if soja else 0
    fator=(pb_s/pb_f) if pb_f else 0
    a,b,c=st.columns(3)
    a.metric("FortiPro posto",br_money(posto))
    b.metric("Economia 1:1",br_money(eco),f"{pct:.1f}%")
    c.metric("Equivalente em PB",br_money(posto*fator))
    st.caption("Equivalência por PB é referência simplificada, não formulação nutricional.")

with tab2:
    st.subheader("Cotação automática no MaisFrete")
    c1,c2=st.columns(2)
    with c1:
        origem=st.text_input("Cidade de origem","Uberlândia")
        uf_o=st.text_input("UF origem","MG",max_chars=2).upper()
    with c2:
        destino=st.text_input("Cidade de destino","Viçosa")
        uf_d=st.text_input("UF destino","MG",max_chars=2).upper()
    a,b,c=st.columns(3)
    with a: eixos=st.selectbox("Eixos",[3,4,5,6,7,9],index=4)
    with b: peso=st.number_input("Peso (t)",min_value=1.0,value=36.0,step=1.0)
    with c: margem=st.number_input("Margem (%)",min_value=0.0,max_value=100.0,value=25.0,step=1.0)

    if st.button("Calcular logística",type="primary",use_container_width=True):
        with st.spinner("Consultando MaisFrete..."):
            try:
                r=cotar(origem,uf_o,destino,uf_d,eixos,peso,margem)
                st.session_state["r"]=r
                st.session_state["frete_emp_t"]=r["frete_emp_t"]
            except Exception as e:
                st.error("Falha na automação do MaisFrete.")
                st.exception(e)

    r=st.session_state.get("r")
    if r:
        st.success(f'{r["origem"]} → {r["destino"]}')
        x1,x2,x3,x4=st.columns(4)
        x1.metric("Distância",f'{r["km"]:.0f} km')
        x2.metric("Frete mínimo",br_money(r["frete_min"]))
        x3.metric("Frete empresa",br_money(r["frete_emp"]))
        x4.metric("Frete empresa / t",br_money(r["frete_emp_t"]))

with tab3:
    st.info("V3 entra depois da confirmação do NCM e tratamento fiscal real da NF do FortiPro.")
