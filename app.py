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


URL = "https://consulta.maisfrete.com.br/exe_consulta_frete_minimo.php"


st.set_page_config(
    page_title="FortiPro | Preço Posto",
    page_icon="🚚",
    layout="wide"
)


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
        txt.replace("R$", "")
        .strip()
        .replace(".", "")
        .replace(",", ".")
    )

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        txt
    )

    return float(
        m.group()
    ) if m else None


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
# BUSCA A CIDADE E DESCOBRE A UF AUTOMATICAMENTE
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

        const buscaLimpa =
            limpar(busca);

        // Primeiro tenta achar correspondência exata
        // do nome antes da "/ UF".

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

        // Se não encontrar exata,
        // usa o primeiro resultado do MaisFrete.

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

        # -------------------------------------------------
        # ORIGEM + UF AUTOMÁTICA
        # -------------------------------------------------

        origem_resultado = (
            selecionar_cidade_automatica(
                driver,
                "input-0",
                "f_cd_cidade_origem",
                normalizar(origem)
            )
        )

        if not origem_resultado.get(
            "ok"
        ):

            raise RuntimeError(
                "Origem não encontrada."
            )

        # -------------------------------------------------
        # DESTINO + UF AUTOMÁTICA
        # -------------------------------------------------

        destino_resultado = (
            selecionar_cidade_automatica(
                driver,
                "input-1",
                "f_cd_cidade_destino",
                normalizar(destino)
            )
        )

        if not destino_resultado.get(
            "ok"
        ):

            raise RuntimeError(
                "Destino não encontrado."
            )

        # -------------------------------------------------
        # ROTEIRIZAÇÃO
        # -------------------------------------------------

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
                    .get_attribute(
                        "value"
                    )
                    or ""
                ).strip()
        )

        km_texto = (
            driver
            .find_element(
                By.ID,
                "qtKmRodado"
            )
            .get_attribute(
                "value"
            )
            .strip()
        )

        # -------------------------------------------------
        # EIXOS / PESO / MARGEM / ICMS
        # -------------------------------------------------

        driver.execute_script(
            """
            const valores =
                arguments[0];

            Object.entries(
                valores
            )
            .forEach(
                ([id, valor]) => {

                    const campo =
                        document.getElementById(
                            id
                        );

                    if (!campo) {
                        return;
                    }

                    campo.value =
                        valor;

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
                }
            );
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

        # -------------------------------------------------
        # CALCULAR
        # -------------------------------------------------

        if not clicar(
            driver,
            "calcular"
        ):

            raise RuntimeError(
                "Botão Calcular não encontrado."
            )

        # -------------------------------------------------
        # CAPTURA GRANEL SÓLIDO
        # -------------------------------------------------

        def valores_granel(d):

            return d.execute_script(
                r"""
                const linhas =
                    [
                        ...document
                        .querySelectorAll(
                            "tr"
                        )
                    ];

                const linha =
                    linhas.find(l => {

                        const texto =
                            (
                                l.innerText ||
                                ""
                            ).trim();

                        return (
                            texto.startsWith(
                                "Granel Sólido"
                            )
                            &&
                            (
                                texto.match(
                                    /R\$/g
                                )
                                ||
                                []
                            ).length >= 7
                        );
                    });

                if (!linha) {
                    return null;
                }

                const texto =
                    (
                        linha.innerText ||
                        ""
                    ).trim();

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

        # -------------------------------------------------
        # VALORES MAISFRETE
        # -------------------------------------------------

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

        # -------------------------------------------------
        # PEDÁGIO / TONELADA
        # -------------------------------------------------

        pedagio_t = (
            pedagio_total /
            float(peso)
            if peso
            else 0.0
        )

        # -------------------------------------------------
        # FRETE + PEDÁGIO
        # -------------------------------------------------

        frete_base_t = (
            frete_empresa_t +
            pedagio_t
        )

        # -------------------------------------------------
        # MARGEM DE SEGURANÇA
        # -------------------------------------------------

        margem_seguranca_t = (
            frete_base_t *
            (
                margem_seguranca /
                100
            )
        )

        # -------------------------------------------------
        # FRETE FINAL
        # -------------------------------------------------

        frete_final_t = (
            frete_base_t +
            margem_seguranca_t
        )

        frete_final_carga = (
            frete_final_t *
            float(peso)
        )

        # -------------------------------------------------
        # RESULTADO
        # -------------------------------------------------

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
                icms
        }

    finally:

        driver.quit()


# =========================================================
# TÍTULO / ABAS
# =========================================================

st.title(
    "FortiPro | Formação de preço"
)


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
        "Dados conforme a NF enviada pela Inpasa."
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
        "* Conforme enquadramento legal aplicável à operação."
    )

    st.divider()

    forti_fob = st.number_input(
        "Preço FOB FortiPro (R$/t)",
        min_value=0.0,
        value=1445.0,
        step=10.0
    )

    st.session_state[
        "forti_fob"
    ] = forti_fob

    st.info(
        "O ICMS é informado na V2 porque depende da operação de transporte."
    )


# =========================================================
# V2 — LOGÍSTICA
# =========================================================

with tab2:

    st.subheader(
        "Cotação automática no MaisFrete"
    )

    st.caption(
        "Digite somente as cidades. O estado será identificado automaticamente pelo MaisFrete."
    )

    c1, c2 = st.columns(
        2
    )

    with c1:

        origem = st.text_input(
            "Cidade de origem",
            "Uberlândia"
        )

    with c2:

        destino = st.text_input(
            "Cidade de destino",
            "Viçosa"
        )

    # -----------------------------------------------------
    # EIXOS
    # -----------------------------------------------------

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
        f"{peso:.0f} toneladas."
    )

    # -----------------------------------------------------
    # AJUSTES
    # -----------------------------------------------------

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
                "Informe conforme a operação. "
                "Deixe 0 quando não aplicável."
            )
        )

    with c:

        margem_seguranca = st.number_input(
            "Margem de segurança (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0
        )

    # -----------------------------------------------------
    # BOTÃO
    # -----------------------------------------------------

    if st.button(
        "Calcular logística",
        type="primary",
        use_container_width=True
    ):

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

    resultado = st.session_state.get(
        "resultado_logistica"
    )

    # -----------------------------------------------------
    # RESULTADO LOGÍSTICO
    # -----------------------------------------------------

    if resultado:

        st.success(
            f'{resultado["origem"]} → '
            f'{resultado["destino"]}'
        )

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
            f"{eixos} eixos • "
            f"{peso:.0f} t • "
            f"ICMS {icms:.1f}% • "
            f"margem MaisFrete "
            f"{margem_empresa:.0f}% • "
            f"margem segurança "
            f"{margem_seguranca:.1f}%"
        )


# =========================================================
# V3 — RESULTADO
# =========================================================

with tab3:

    st.subheader(
        "FortiPro posto na propriedade"
    )

    forti_fob_final = (
        st.session_state.get(
            "forti_fob",
            1445.0
        )
    )

    frete_final_t = (
        st.session_state.get(
            "frete_final_t"
        )
    )

    # -----------------------------------------------------
    # AINDA NÃO CALCULOU FRETE
    # -----------------------------------------------------

    if frete_final_t is None:

        st.warning(
            "Calcule primeiro a logística na V2 para obter o preço posto na propriedade."
        )

    # -----------------------------------------------------
    # JÁ POSSUI FRETE
    # -----------------------------------------------------

    else:

        forti_posto = (
            forti_fob_final +
            frete_final_t
        )

        r1, r2, r3 = st.columns(
            3
        )

        r1.metric(
            "FOB FortiPro",
            br_money(
                forti_fob_final
            )
        )

        r2.metric(
            "Logística / t",
            br_money(
                frete_final_t
            )
        )

        r3.metric(
            "FortiPro posto",
            br_money(
                forti_posto
            )
        )

        st.success(
            "Preço estimado do FortiPro entregue "
            "na propriedade: "
            +
            br_money(
                forti_posto
            )
            +
            "/t."
        )

        st.caption(
            "FortiPro posto = preço FOB + logística final por tonelada."
        )

        # =================================================
        # COMPARAÇÃO COM FARELO DE SOJA
        # =================================================

        st.divider()

        st.subheader(
            "Comparativo de proteína posta"
        )

        st.caption(
            "Comparação feita entre os dois produtos já considerados na propriedade."
        )

        c1, c2 = st.columns(
            2
        )

        with c1:

            st.markdown(
                "### FortiPro"
            )

            pb_forti = st.number_input(
                "PB FortiPro (%)",
                min_value=0.1,
                max_value=100.0,
                value=35.0,
                step=0.5
            )

        with c2:

            st.markdown(
                "### Farelo de soja"
            )

            soja_posto = st.number_input(
                "Farelo de soja posto (R$/t)",
                min_value=0.0,
                value=2130.0,
                step=10.0
            )

            pb_soja = st.number_input(
                "PB Farelo de soja (%)",
                min_value=0.1,
                max_value=100.0,
                value=46.0,
                step=0.5
            )

        # -------------------------------------------------
        # KG PB / TONELADA
        # -------------------------------------------------

        kg_pb_forti = (
            pb_forti *
            10
        )

        kg_pb_soja = (
            pb_soja *
            10
        )

        # -------------------------------------------------
        # CUSTO / KG PB
        # -------------------------------------------------

        custo_pb_forti = (
            forti_posto /
            kg_pb_forti
            if kg_pb_forti
            else 0
        )

        custo_pb_soja = (
            soja_posto /
            kg_pb_soja
            if kg_pb_soja
            else 0
        )

        # -------------------------------------------------
        # DIFERENÇA
        # -------------------------------------------------

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
            else 0
        )

        # -------------------------------------------------
        # RESULTADOS
        # -------------------------------------------------

        p1, p2, p3, p4 = st.columns(
            4
        )

        p1.metric(
            "FortiPro posto",
            br_money(
                forti_posto
            )
        )

        p2.metric(
            "Farelo posto",
            br_money(
                soja_posto
            )
        )

        p3.metric(
            "Custo/kg PB FortiPro",
            br_money(
                custo_pb_forti
            )
        )

        p4.metric(
            "Custo/kg PB soja",
            br_money(
                custo_pb_soja
            )
        )

        # -------------------------------------------------
        # INTERPRETAÇÃO
        # -------------------------------------------------

        if diferenca_pct < 0:

            st.success(
                f"O FortiPro está "
                f"{abs(diferenca_pct):.1f}% "
                "mais barato por kg de proteína bruta "
                "que o farelo de soja, considerando "
                "os preços postos informados."
            )

        elif diferenca_pct > 0:

            st.warning(
                f"O FortiPro está "
                f"{diferenca_pct:.1f}% "
                "mais caro por kg de proteína bruta "
                "que o farelo de soja, considerando "
                "os preços postos informados."
            )

        else:

            st.info(
                "FortiPro e farelo de soja possuem "
                "o mesmo custo por kg de proteína bruta."
            )

        st.caption(
            "Custo/kg PB = preço posto da tonelada ÷ quantidade de proteína bruta presente em 1 tonelada."
        )
