import os
import re
import unicodedata

import streamlit as st

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =========================================================
# CONFIGURAÇÕES
# =========================================================

URL = "https://consulta.maisfrete.com.br/exe_consulta_frete_minimo.php"

st.set_page_config(
    page_title="FortiPro | Preço Posto",
    page_icon="🚚",
    layout="wide"
)


# =========================================================
# CAPACIDADE AUTOMÁTICA POR EIXOS
# =========================================================

CAPACIDADE_EIXOS = {
    2: 10.0,
    3: 14.0,
    4: 17.0,
    5: 26.0,
    6: 31.0,
    7: 36.0,
    8: 40.0,
    9: 49.0
}


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def br_money(v):

    if v is None:
        return "—"

    return (
        f"R$ {v:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def br_to_float(txt):

    if not txt:
        return None

    txt = (
        txt
        .replace("R$", "")
        .strip()
        .replace(".", "")
        .replace(",", ".")
    )

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        txt
    )

    return float(m.group()) if m else None


def normalizar(s):

    return "".join(
        c
        for c in unicodedata.normalize(
            "NFD",
            s
        )
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


# =========================================================
# SELENIUM / CHROMIUM
# =========================================================

def get_driver():

    opts = Options()

    argumentos = [
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1440,1200"
    ]

    for arg in argumentos:
        opts.add_argument(arg)

    for caminho in [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser"
    ]:

        if os.path.exists(caminho):
            opts.binary_location = caminho
            break

    for caminho in [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver"
    ]:

        if os.path.exists(caminho):

            return webdriver.Chrome(
                service=Service(caminho),
                options=opts
            )

    return webdriver.Chrome(
        options=opts
    )


# =========================================================
# BUSCA CIDADE E IDENTIFICA UF AUTOMATICAMENTE
# =========================================================

def selecionar_cidade_automatica(
    driver,
    input_id,
    hidden_id,
    busca
):

    js = r"""
    const done = arguments[arguments.length - 1];

    const inputId = arguments[0];
    const hiddenId = arguments[1];
    const busca = arguments[2];

    const limpar = texto =>
        (texto || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .trim();

    const url =
        "/lib/jaguar/AjaxIframe.php" +
        "?c=Cidade" +
        "&a=obterCidadesAutoComplete" +
        "&p%5BdsItem%5D=" +
        encodeURIComponent(busca);

    fetch(
        url,
        {
            credentials: "same-origin",
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        }
    )
    .then(r => r.json())
    .then(dados => {

        const buscaLimpa = limpar(busca);

        let cidade = dados.find(item => {

            const descricao =
                item.description || "";

            const nomeCidade =
                descricao
                .split("/")[0]
                .trim();

            return (
                limpar(nomeCidade) === buscaLimpa
            );
        });

        if (!cidade && dados.length > 0) {
            cidade = dados[0];
        }

        if (!cidade) {

            done({
                ok: false,
                dados: dados
            });

            return;
        }

        const descricao =
            cidade.description || "";

        const partes =
            descricao.split("/");

        const nomeCidade =
            partes[0]
            ? partes[0].trim()
            : "";

        const uf =
            partes[1]
            ? partes[1].trim()
            : "";

        const campoVisivel =
            document.getElementById(
                inputId
            );

        const campoOculto =
            document.getElementById(
                hiddenId
            );

        campoVisivel.value =
            cidade.description;

        campoOculto.value =
            cidade.value;

        campoVisivel.dispatchEvent(
            new Event(
                "input",
                {bubbles: true}
            )
        );

        campoVisivel.dispatchEvent(
            new Event(
                "change",
                {bubbles: true}
            )
        );

        campoOculto.dispatchEvent(
            new Event(
                "change",
                {bubbles: true}
            )
        );

        done({
            ok: true,
            cidade: cidade,
            nome: nomeCidade,
            uf: uf
        });
    })
    .catch(
        erro =>
            done({
                ok: false,
                erro: String(erro)
            })
    );
    """

    return driver.execute_async_script(
        js,
        input_id,
        hidden_id,
        busca
    )


# =========================================================
# CLICA EM BOTÃO
# =========================================================

def clicar(
    driver,
    texto
):

    return driver.execute_script(
        """
        const texto =
            arguments[0]
            .toLowerCase();

        const elementos =
            [
                ...document.querySelectorAll(
                    "button," +
                    "input[type=button]," +
                    "input[type=submit]"
                )
            ];

        const botao =
            elementos.find(
                el =>
                    (
                        el.innerText ||
                        el.value ||
                        ""
                    )
                    .trim()
                    .toLowerCase()
                    .includes(texto)
            );

        if (!botao) {
            return false;
        }

        botao.click();

        return true;
        """,
        texto
    )


# =========================================================
# COTAÇÃO MAISFRETE
# =========================================================

def cotar(
    origem,
    destino,
    eixos,
    peso,
    margem_empresa,
    icms,
    margem_seguranca
):

    driver = get_driver()

    try:

        driver.get(URL)

        wait = WebDriverWait(
            driver,
            40
        )

        wait.until(
            EC.presence_of_element_located(
                (
                    By.ID,
                    "input-0"
                )
            )
        )


        # =================================================
        # ORIGEM
        # =================================================

        origem_resultado = (
            selecionar_cidade_automatica(
                driver,
                "input-0",
                "f_cd_cidade_origem",
                normalizar(origem)
            )
        )

        if not origem_resultado.get("ok"):

            raise RuntimeError(
                "Origem não encontrada."
            )


        # =================================================
        # DESTINO
        # =================================================

        destino_resultado = (
            selecionar_cidade_automatica(
                driver,
                "input-1",
                "f_cd_cidade_destino",
                normalizar(destino)
            )
        )

        if not destino_resultado.get("ok"):

            raise RuntimeError(
                "Destino não encontrado."
            )


        # =================================================
        # ROTEIRIZAÇÃO
        # =================================================

        if not clicar(
            driver,
            "roteirizar"
        ):

            raise RuntimeError(
                "Botão Roteirizar não encontrado."
            )

        wait.until(
            lambda d:
                (
                    d.find_element(
                        By.ID,
                        "qtKmRodado"
                    )
                    .get_attribute("value")
                    or ""
                ).strip()
        )

        km_texto = (
            driver
            .find_element(
                By.ID,
                "qtKmRodado"
            )
            .get_attribute("value")
            .strip()
        )


        # =================================================
        # PREENCHE PARÂMETROS
        # =================================================

        driver.execute_script(
            """
            const valores = arguments[0];

            Object.entries(valores)
            .forEach(([id, valor]) => {

                const campo =
                    document.getElementById(id);

                if (!campo) {
                    return;
                }

                campo.value = valor;

                campo.dispatchEvent(
                    new Event(
                        "input",
                        {bubbles: true}
                    )
                );

                campo.dispatchEvent(
                    new Event(
                        "change",
                        {bubbles: true}
                    )
                );
            });
            """,
            {

                "qtEixos":
                    str(eixos),

                "prMargemTransportadora":
                    str(
                        margem_empresa
                    ).replace(
                        ".",
                        ","
                    ),

                "prIcms":
                    (
                        str(icms)
                        .replace(
                            ".",
                            ","
                        )
                        if icms > 0
                        else ""
                    ),

                "vlPesoTonelada":
                    f"{float(peso):.2f}"
                    .replace(
                        ".",
                        ","
                    )
            }
        )


        # =================================================
        # CALCULAR
        # =================================================

        if not clicar(
            driver,
            "calcular"
        ):

            raise RuntimeError(
                "Botão Calcular não encontrado."
            )


        # =================================================
        # CAPTURA LINHA GRANEL SÓLIDO
        # =================================================

        def valores_granel(d):

            return d.execute_script(
                r"""
                const linhas =
                    [...document.querySelectorAll("tr")];

                const linha =
                    linhas.find(l => {

                        const texto =
                            (l.innerText || "").trim();

                        return (
                            texto.startsWith(
                                "Granel Sólido"
                            )
                            &&
                            (
                                texto.match(/R\$/g)
                                || []
                            ).length >= 7
                        );
                    });

                if (!linha) {
                    return null;
                }

                const texto =
                    (linha.innerText || "").trim();

                const valores =
                    texto.match(
                        /R\$\s*[0-9\.]+(?:,[0-9]+)?/g
                    );

                if (
                    !valores ||
                    valores.length < 7
                ) {
                    return null;
                }

                return {
                    texto: texto,
                    valores: valores
                };
                """
            )

        dados_granel = wait.until(
            valores_granel
        )

        valores = dados_granel[
            "valores"
        ]


        # =================================================
        # VALORES RETORNADOS
        # =================================================

        # 0 = KM por eixo
        # 1 = carga/descarga
        # 2 = frete mínimo total
        # 3 = frete mínimo / t
        # 4 = frete empresa total
        # 5 = frete empresa / t
        # 6 = pedágio

        frete_minimo = br_to_float(
            valores[2]
        )

        frete_minimo_t = br_to_float(
            valores[3]
        )

        frete_empresa = br_to_float(
            valores[4]
        )

        frete_empresa_t = br_to_float(
            valores[5]
        )

        pedagio_total = br_to_float(
            valores[6]
        )


        # =================================================
        # PEDÁGIO POR TONELADA
        # =================================================

        pedagio_t = (
            pedagio_total /
            float(peso)
            if peso
            else 0.0
        )


        # =================================================
        # FRETE + PEDÁGIO
        # =================================================

        frete_base_t = (
            frete_empresa_t +
            pedagio_t
        )


        # =================================================
        # MARGEM DE SEGURANÇA
        # =================================================

        margem_seguranca_t = (
            frete_base_t *
            (
                margem_seguranca /
                100
            )
        )


        # =================================================
        # FRETE FINAL
        # =================================================

        frete_final_t = (
            frete_base_t +
            margem_seguranca_t
        )

        frete_final_carga = (
            frete_final_t *
            float(peso)
        )


        # =================================================
        # RETORNO
        # =================================================

        return {

            "origem":
                origem_resultado[
                    "cidade"
                ][
                    "description"
                ],

            "origem_uf":
                origem_resultado[
                    "uf"
                ],

            "destino":
                destino_resultado[
                    "cidade"
                ][
                    "description"
                ],

            "destino_uf":
                destino_resultado[
                    "uf"
                ],

            "km":
                br_to_float(
                    km_texto
                ),

            "frete_min":
                frete_minimo,

            "frete_min_t":
                frete_minimo_t,

            "frete_emp":
                frete_empresa,

            "frete_emp_t":
                frete_empresa_t,

            "pedagio_total":
                pedagio_total,

            "pedagio_t":
                pedagio_t,

            "frete_base_t":
                frete_base_t,

            "margem_seguranca_pct":
                margem_seguranca,

            "margem_seguranca_t":
                margem_seguranca_t,

            "frete_final_t":
                frete_final_t,

            "frete_final_carga":
                frete_final_carga,

            "icms":
                icms,

            "eixos":
                eixos,

            "peso":
                peso
        }

    finally:

        driver.quit()


# =========================================================
# CABEÇALHO
# =========================================================

st.title(
    "FortiPro | Formação de preço"
)

st.caption(
    "Ferramenta para análise fiscal, logística e comparação econômica do FortiPro."
)


# =========================================================
# ABAS
# =========================================================

tab1, tab2, tab3 = st.tabs(
    [
        "V1 • Fiscal",
        "V2 • Logística",
        "V3 • Resultado"
    ]
)


# =========================================================
# V1 — FISCAL
# =========================================================

with tab1:

    st.subheader(
        "Dados fiscais do FortiPro"
    )

    st.caption(
        "Dados conforme a documentação fiscal analisada do produto."
    )

    f1, f2, f3, f4 = st.columns(
        4
    )

    f1.metric(
        "NCM",
        "2302.10.00"
    )

    f2.metric(
        "CST",
        "090"
    )

    f3.metric(
        "IPI",
        "0%"
    )

    f4.metric(
        "PIS/Cofins",
        "Suspensos*"
    )

    st.caption(
        "* Conforme o enquadramento legal aplicável à operação."
    )

    st.divider()

    st.info(
        "O ICMS não é fixado nesta aba. "
        "Ele é informado na V2 conforme a operação logística analisada."
    )


# =========================================================
# V2 — LOGÍSTICA
# =========================================================

with tab2:

    st.subheader(
        "Cotação automática no MaisFrete"
    )

    st.caption(
        "Digite somente as cidades. "
        "A UF será identificada automaticamente pelo MaisFrete."
    )


    # =====================================================
    # ORIGEM E DESTINO
    # =====================================================

    c1, c2 = st.columns(
        2
    )

    with c1:

        origem = st.text_input(
            "Cidade de origem",
            value="Uberlândia"
        )

    with c2:

        destino = st.text_input(
            "Cidade de destino",
            value="Viçosa"
        )


    # =====================================================
    # EIXOS
    # =====================================================

    eixos = st.selectbox(
        "Quantidade de eixos",
        options=[
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9
        ],
        index=5,
        format_func=lambda x:
            f"{x} eixos"
    )

    peso = CAPACIDADE_EIXOS[
        eixos
    ]

    st.info(
        f"Capacidade considerada automaticamente: "
        f"{peso:.0f} toneladas para um veículo de "
        f"{eixos} eixos."
    )


    # =====================================================
    # PARÂMETROS
    # =====================================================

    a, b, c = st.columns(
        3
    )

    with a:

        margem_empresa = st.number_input(
            "Margem empresa MaisFrete (%)",
            min_value=0.0,
            max_value=100.0,
            value=25.0,
            step=1.0
        )

    with b:

        icms = st.number_input(
            "ICMS (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help=(
                "Informe a alíquota utilizada "
                "na operação de transporte."
            )
        )

    with c:

        margem_seguranca = st.number_input(
            "Margem de segurança (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help=(
                "Margem adicional aplicada ao "
                "frete + pedágio para aproximar "
                "o valor estimado da realidade de mercado."
            )
        )


    # =====================================================
    # CALCULAR
    # =====================================================

    if st.button(
        "Calcular logística",
        type="primary",
        use_container_width=True
    ):

        if not origem.strip():

            st.error(
                "Informe a cidade de origem."
            )

        elif not destino.strip():

            st.error(
                "Informe a cidade de destino."
            )

        else:

            with st.spinner(
                "Consultando MaisFrete..."
            ):

                try:

                    resultado = cotar(
                        origem,
                        destino,
                        eixos,
                        peso,
                        margem_empresa,
                        icms,
                        margem_seguranca
                    )

                    st.session_state[
                        "resultado_logistica"
                    ] = resultado

                    st.session_state[
                        "frete_final_t"
                    ] = resultado[
                        "frete_final_t"
                    ]

                except Exception as erro:

                    st.error(
                        "Falha na automação do MaisFrete."
                    )

                    st.exception(
                        erro
                    )


    # =====================================================
    # RESULTADO DA LOGÍSTICA
    # =====================================================

    resultado = st.session_state.get(
        "resultado_logistica"
    )

    if resultado:

        st.divider()

        st.success(
            f'{resultado["origem"]} → '
            f'{resultado["destino"]}'
        )

        # -------------------------------------------------
        # PRIMEIRA LINHA
        # -------------------------------------------------

        x1, x2, x3, x4 = st.columns(
            4
        )

        x1.metric(
            "Distância",
            f'{resultado["km"]:.0f} km'
        )

        x2.metric(
            "Frete mínimo",
            br_money(
                resultado[
                    "frete_min"
                ]
            )
        )

        x3.metric(
            "Frete empresa",
            br_money(
                resultado[
                    "frete_emp"
                ]
            )
        )

        x4.metric(
            "Frete empresa / t",
            br_money(
                resultado[
                    "frete_emp_t"
                ]
            )
        )


        # -------------------------------------------------
        # SEGUNDA LINHA
        # -------------------------------------------------

        y1, y2, y3 = st.columns(
            3
        )

        y1.metric(
            "Pedágio",
            br_money(
                resultado[
                    "pedagio_total"
                ]
            )
        )

        y2.metric(
            "Pedágio / t",
            br_money(
                resultado[
                    "pedagio_t"
                ]
            )
        )

        y3.metric(
            "Frete + pedágio / t",
            br_money(
                resultado[
                    "frete_base_t"
                ]
            )
        )


        # -------------------------------------------------
        # TERCEIRA LINHA
        # -------------------------------------------------

        z1, z2, z3 = st.columns(
            3
        )

        z1.metric(
            "Margem segurança / t",
            br_money(
                resultado[
                    "margem_seguranca_t"
                ]
            )
        )

        z2.metric(
            "Frete final / t",
            br_money(
                resultado[
                    "frete_final_t"
                ]
            )
        )

        z3.metric(
            "Frete final da carga",
            br_money(
                resultado[
                    "frete_final_carga"
                ]
            )
        )

        st.caption(
            f'{resultado["eixos"]} eixos • '
            f'{resultado["peso"]:.0f} t • '
            f'ICMS {resultado["icms"]:.1f}% • '
            f'margem MaisFrete {margem_empresa:.0f}% • '
            f'margem segurança '
            f'{resultado["margem_seguranca_pct"]:.1f}%'
        )


# =========================================================
# V3 — RESULTADO
# =========================================================

with tab3:

    st.subheader(
        "Comparativo posto na propriedade"
    )

    frete_final_t = st.session_state.get(
        "frete_final_t"
    )


    # =====================================================
    # SEM FRETE CALCULADO
    # =====================================================

    if frete_final_t is None:

        st.warning(
            "Calcule primeiro a logística na V2 "
            "para obter os preços postos."
        )


    # =====================================================
    # COM FRETE CALCULADO
    # =====================================================

    else:

        st.caption(
            "O mesmo frete por tonelada é aplicado "
            "ao FortiPro e ao farelo de soja."
        )


        # =================================================
        # PREÇOS E PB
        # =================================================

        c1, c2 = st.columns(
            2
        )


        # -------------------------------------------------
        # FORTIPRO
        # -------------------------------------------------

        with c1:

            st.markdown(
                "### FortiPro"
            )

            preco_forti = st.number_input(
                "Preço FortiPro (R$/t)",
                min_value=0.0,
                value=1445.0,
                step=10.0,
                key="preco_forti_resultado"
            )

            pb_forti = st.number_input(
                "Proteína bruta FortiPro (%)",
                min_value=0.1,
                max_value=100.0,
                value=35.0,
                step=0.5,
                key="pb_forti_resultado"
            )


        # -------------------------------------------------
        # FARELO DE SOJA
        # -------------------------------------------------

        with c2:

            st.markdown(
                "### Farelo de soja"
            )

            preco_soja = st.number_input(
                "Preço Farelo de soja (R$/t)",
                min_value=0.0,
                value=2130.0,
                step=10.0,
                key="preco_soja_resultado"
            )

            pb_soja = st.number_input(
                "Proteína bruta Farelo de soja (%)",
                min_value=0.1,
                max_value=100.0,
                value=46.0,
                step=0.5,
                key="pb_soja_resultado"
            )


        # =================================================
        # PREÇOS POSTOS
        # =================================================

        forti_posto = (
            preco_forti +
            frete_final_t
        )

        soja_posto = (
            preco_soja +
            frete_final_t
        )


        # =================================================
        # KG DE PROTEÍNA POR TONELADA
        # =================================================

        kg_pb_forti = (
            pb_forti *
            10
        )

        kg_pb_soja = (
            pb_soja *
            10
        )


        # =================================================
        # CUSTO POR KG DE PROTEÍNA BRUTA
        # =================================================

        custo_pb_forti = (
            forti_posto /
            kg_pb_forti
            if kg_pb_forti
            else 0.0
        )

        custo_pb_soja = (
            soja_posto /
            kg_pb_soja
            if kg_pb_soja
            else 0.0
        )


        # =================================================
        # DIFERENÇA PERCENTUAL
        # =================================================

        diferenca_pct = (
            (
                custo_pb_forti /
                custo_pb_soja
                -
                1
            )
            *
            100
            if custo_pb_soja
            else 0.0
        )


        # =================================================
        # PREÇOS POSTOS
        # =================================================

        st.divider()

        st.markdown(
            "### Preços postos"
        )

        p1, p2, p3 = st.columns(
            3
        )

        p1.metric(
            "Frete aplicado / t",
            br_money(
                frete_final_t
            )
        )

        p2.metric(
            "FortiPro posto",
            br_money(
                forti_posto
            )
        )

        p3.metric(
            "Farelo de soja posto",
            br_money(
                soja_posto
            )
        )

        st.caption(
            "Preço posto = preço do produto + frete final por tonelada."
        )


        # =================================================
        # CUSTO DA PROTEÍNA
        # =================================================

        st.divider()

        st.markdown(
            "### Custo da proteína bruta"
        )

        q1, q2 = st.columns(
            2
        )

        q1.metric(
            "Custo/kg PB FortiPro",
            br_money(
                custo_pb_forti
            )
        )

        q2.metric(
            "Custo/kg PB Farelo de soja",
            br_money(
                custo_pb_soja
            )
        )


        # =================================================
        # RESULTADO COMERCIAL
        # =================================================

        st.divider()

        st.markdown(
            "### Resultado"
        )

        if diferenca_pct < 0:

            st.success(
                f"O FortiPro está "
                f"{abs(diferenca_pct):.1f}% "
                "mais barato por kg de proteína bruta "
                "que o farelo de soja."
            )

        elif diferenca_pct > 0:

            st.warning(
                f"O FortiPro está "
                f"{diferenca_pct:.1f}% "
                "mais caro por kg de proteína bruta "
                "que o farelo de soja."
            )

        else:

            st.info(
                "FortiPro e farelo de soja possuem "
                "o mesmo custo por kg de proteína bruta."
            )

        st.caption(
            "Custo/kg PB = preço posto da tonelada ÷ "
            "quantidade de proteína bruta presente em 1 tonelada."
        )
