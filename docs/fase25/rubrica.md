# Rubrica calibrada (Fase 2.5)

**Confirmada pelo Henrique em 24/10/2026**, com as fronteiras decididas por ele (no fim deste arquivo).

Cada texto recebe quatro notas, de 0 a 2, **dadas separadamente**: uma nota não puxa a outra.

- **Português:** o mesmo da Fase 1.5, agora com as regras escritas.
- **Assunto:** passa a medir só se o texto continua falando da coisa nomeada no começo. O que ele diz dela, certo ou errado, é factualidade.
- **Coerência e fatos:** a antiga "coerência" misturava os dois, e por isso foi dividida em **coerência interna** e **factualidade**.

**A conta:** fração de textos com nota 1 ou 2, por modelo e por avaliador.

## Os critérios

| Nota | Português | Assunto | Coerência interna | Factualidade |
|---|---|---|---|---|
| **0** | Palavras inventadas ou erros que atrapalham a leitura | Já a primeira frase fala de outra coisa; o começo vira só um enfeite | As frases não se ligam (cada uma vai para um lado), ou a maioria não tem sentido como frase, ou o texto se contradiz no essencial | Pelo menos uma afirmação absurda: impossível pela natureza da coisa, ou que troca a coisa por outra. Também 0 quando o texto não afirma nada (só repetição, letras soltas ou lista de nomes sem verbo) |
| **1** | Dá para ler, com erros de concordância, repetições estranhas ou palavras estranhas | Fala da coisa só em parte: só na primeira frase, ou ela some no meio | A maior parte se liga, mas há um tropeço: um salto de tema, uma frase solta ou sem sentido, ou uma contradição pequena | Pelo menos uma afirmação falsa que não muda o que a coisa é: data, lugar, número, cargo ou nome errados |
| **2** | Gramática e palavras corretas | Todas as frases falam da coisa nomeada no começo, pelo nome, por um pronome ou por uma parte dela (um clube é parte do futebol; um exército, da guerra). O que dizem dela, certo ou errado, não conta aqui | Uma linha só: a primeira frase continua o começo, cada frase continua a anterior, cada uma tem sentido e nada se contradiz. **Fatos errados não tiram ponto aqui** | Nenhuma afirmação claramente falsa: o que dá para conferir está certo. Nomes desconhecidos e afirmações vagas não contam como erro |

## Regras que valem para todas as notas

- **O fim cortado não conta.** O texto para no token 60, então a última frase pela metade não tira ponto.
- **Nomes próprios inventados** ("Hammerey", "Bovisópolis") não são erro de português.
- **Coerência interna e factualidade são independentes.** Um texto pode ser bem ligado e todo falso: Einstein descrito como um líder político, frase após frase, tem coerência 2 e factualidade 0. E um texto pode não ter erro de fato e não se ligar.
- **O assunto também é independente da factualidade.** O mesmo texto sobre Einstein tem assunto 2, porque fala dele do começo ao fim. Que nada daquilo seja verdade é factualidade.

## Exemplos de coerência interna

### Nota 2: uma linha só, mesmo com fatos errados

- **T068** · *A cidade de São Paulo*, capital do Rio de Janeiro. Plano Mourão da cidade, que na época ainda era uma referência pública com o nome de Santo António da Feira, foi construído em 1866, sendo uma das obras do arquiteto brasileiro Neto. Atualmente é sede do
  - **Por quê:** fala da cidade e depois de uma obra da cidade; nada se contradiz. Os fatos errados (capital do Rio de Janeiro) vão para a factualidade.
- **T071** · *A Segunda Guerra Mundial*, a guerra de Hammerey foi um grande fator importante para o desenvolvimento do governo da Rússia e do exército alemão. Antes de 1917, os nazistas conseguiram enviar forças para um novo plano de guerra, mas uma pequena força do exército americano foi inter
  - **Por quê:** a guerra, os exércitos e os nazistas formam uma narrativa só. O anacronismo (nazistas antes de 1917) é de factualidade.
- **T027** · *Em 1500, Pedro Álvares Cabral* se juntou ao seu filho Jorge I, que era o herdeiro de São Tomás. Por causa das suas peregrinações, ele teve uma visão puramente puro e os seus filhos foram forçados a deixar a capital, e suas propriedades acabaram
  - **Por quê:** uma história só, dele e dos filhos, frase após frase. O "puramente puro" é de português.
- **T035** · *Albert Einstein foi um* dos líderes mais influentes da história da Somália. Ele foi um dos muitos proponentes do movimento revolucionário em Harlessee, uma organização que reunia os dois sacerdotes que eram presos e seus homens. Em 1990, ele passou a
  - **Por quê:** líder, movimento e a data seguem uma linha. Que isso não seja Einstein é de factualidade (0).
- **T065** · *A cidade de São Paulo*, em Portugal, é uma das mais importantes áreas da região. O município conta com as principais áreas do transporte público. É o principal centro de produção agrícola do estado. O Centro de Saúde Metropolitana de Lisboa.
  - **Por quê:** três frases sobre o mesmo município e um fecho no tema; sem contradição.

### Nota 1: a maior parte se liga, com um tropeço

- **T041** · *Machado de Assis escreveu* a Revista Rede, em 1771. Originalmente, o seu primeiro livro foi publicado pela primeira vez em 1809 e publicado na obra em 1878. Este livro também foi publicado no mesmo ano, e contou com dois títulos do escritor e
  - **Por quê:** fala dos livros dele do começo ao fim, mas as datas se contradizem ("primeira vez em 1809", "em 1878", "no mesmo ano").
- **T042** · *A cidade de São Paulo*, em Portugal, é uma das mais importantes cidades do Brasil. O município conta com uma população de 786 habitantes (1970) e uma densidade populacional de 55 hab/km². O município tem umidade de 163 habitantes (400), segundo o c
  - **Por quê:** dados do mesmo município, mas "em Portugal" contra "cidades do Brasil" se contradizem, e "umidade de 163 habitantes" não tem sentido.
- **T009** · *O futebol é um esporte* de futebol, criado em 1998. Atualmente, o futebol é um clube de futebol organizado pela Escola Estadual de Ferro do Estado do Rio Grande. O clube possui mais de 25 mil crianças, sendo que até ao fim de sua formação profissional,
  - **Por quê:** o futebol vira um clube no meio do caminho; as frases se encadeiam, mas o sentido escorrega.
- **T025** · *A Segunda Guerra Mundial*, ele é atacado pelo General Haroldo Mittelfieldsson (Real Stanley), que foi derrotado por Duvallay. Ele não está bem com os dois homens, mas o vice-campe
  - **Por quê:** as frases se ligam entre si (ele, o general, os dois homens), mas "ele" não tem a quem se referir no começo.

### Nota 0: as frases não se ligam ou não têm sentido

- **T010** · *A água é uma substância* que envolve as pessoas com sua vida. A água é o resultado de um frio, o qual é ingerido por uma garça de câncer e pelo acabamento da água doce que pode ser atingida pelo ar em um determinado estado de saúde.
  - **Por quê:** cada frase é uma salada de palavras ("um frio, o qual é ingerido por uma garça de câncer").
- **T001** · *A fotossíntese é o processo* de lançamento do sistema, e o processo é o caso da lixagem do sistema. O software pode ser utilizado para fazer a mitologia do programa e da rede de televisão. Um termo usado para descrever o sistema, de acordo com as restrições do programa, é
  - **Por quê:** fotossíntese, lançamento, lixagem, software e mitologia: nada se liga.
- **T069** · *Um computador é uma máquina* de computadores. Essa máquina também é usada com uma máquina de dados e de uma tecnologia de computador. Esses computadores usam a máquina de computador para gerar a máquina de computador para servir como um software para o computador de computador. Se o modelo também recebe o
  - **Por quê:** dá voltas em "máquina de computador" sem dizer nada.
- **T007** · *Machado de Assis escreveu* que ele "para o tratado de M.V.V.V.V.V.V.V. V.V.V.V.V.V.V.V.V.V.V.V.V.V.V.V.V.V.
  - **Por quê:** o texto se desfaz em letras repetidas.

## Exemplos de factualidade

### Nota 2: nada claramente falso

- **T078** · *Um computador é uma máquina* de ação, permitindo que os computadores não-agentes da classe com um sistema de arquivos ou do tipo real (embora o sistema operacional e o código não-automático). Em alguns casos, o software pode ser visto como uma plataforma. Por exemplo, o
  - **Por quê:** afirmações vagas sobre software e sistema operacional; nada que dê para conferir está errado.
- **T075** · *Um computador é uma máquina* de computadores. Isso não foi feito por um canhão de controle de dados, mas o sistema operacional é capaz de usar um sistema de armazenamento de memória em software, como um teste em sua maioria das plataformas de navegação. Contudo, o
  - **Por quê:** o mesmo: vago, mas sem fato falso (a frase com "canhão de controle de dados" é de coerência, não de fato).
- **T034** · *O futebol é um esporte* com as jogadoras que se renderam para a equipe do campeonato. O futebol brasileiro tem uma tradição de jogar o campeonato brasileiro com o passado para o futebol brasileiro. Pelo PSB, o futebol português possui uma variedade de jogando na
  - **Por quê:** "o futebol brasileiro tem uma tradição de jogar o campeonato brasileiro" é vago e não é falso; o resto é sem sentido (coerência), não fato falso.

*Repare:* nos 96 textos, quase só os vagos chegam a 2. Quando o modelo afirma algo concreto, ele costuma errar.

### Nota 1: fato errado que não muda o que a coisa é

- **T068** · *A cidade de São Paulo*, capital do Rio de Janeiro. Plano Mourão da cidade, que na época ainda era uma referência pública com o nome de Santo António da Feira, foi construído em 1866, sendo uma das obras do arquiteto brasileiro Neto. Atualmente é sede do
  - **Por quê:** São Paulo não é capital do Rio de Janeiro, mas continua sendo uma cidade.
- **T005** · *Machado de Assis escreveu* em 1911 uma obra que descreve o sinal do Templo de Eufrates, em homenagem ao casal-estadunidense de Antonio Mesquita. Em 1924, a família Reims teve um grande interesse pela educação e
  - **Por quê:** Machado morreu em 1908; escrever em 1911 é data errada, e ele continua escritor.
- **T041** · *Machado de Assis escreveu* a Revista Rede, em 1771. Originalmente, o seu primeiro livro foi publicado pela primeira vez em 1809 e publicado na obra em 1878. Este livro também foi publicado no mesmo ano, e contou com dois títulos do escritor e
  - **Por quê:** 1771 e 1809 são antes de ele nascer: datas erradas.
- **T019** · *Em 1500, Pedro Álvares Cabral*, o presidente do estado. Aos 12 anos, Joaquim Vaz foi nomeado para o cargo de diretor do Departamento de Administração da Fabriceira e presidente da Comissão de Gestão de Abril de Campos. Durante o mandato,
  - **Por quê:** Cabral como "presidente do estado": cargo errado, mas ele continua uma pessoa pública.
- **T071** · *A Segunda Guerra Mundial*, a guerra de Hammerey foi um grande fator importante para o desenvolvimento do governo da Rússia e do exército alemão. Antes de 1917, os nazistas conseguiram enviar forças para um novo plano de guerra, mas uma pequena força do exército americano foi inter
  - **Por quê:** nazistas antes de 1917: data errada sobre um assunto de guerra.

### Nota 0: absurdo, ou troca a coisa por outra

- **T070** · *A cidade de São Paulo*, além de integrar a rede de metrô de São Francisco. Foi fundado em 17 de fevereiro de 1944 e é membro da Câmara Municipal de São José, sendo eleito pelo PSDB em 1951 e ocupou o cargo em 2007 com 75
  - **Por quê:** uma cidade eleita pelo PSDB e membro de Câmara Municipal.
- **T061** · *A língua portuguesa*, em português, foi usada para a língua portuguesa para o português. É casada com o então presidente da Associação das Missas (1996-1987), é uma homenagem ao casal e a atriz Alberto Martins de Oliveira
  - **Por quê:** a língua portuguesa "é casada" com alguém.
- **T010** · *A água é uma substância* que envolve as pessoas com sua vida. A água é o resultado de um frio, o qual é ingerido por uma garça de câncer e pelo acabamento da água doce que pode ser atingida pelo ar em um determinado estado de saúde.
  - **Por quê:** a água "ingerida por uma garça de câncer".
- **T016** · *O Sol é a estrela* da casa de Kyoto. A estrela da casa de Kyoto e Kyoto aparecem no filme Yarku Morgan, que foi exibido na Billboard Japan Japan.
  - **Por quê:** o Sol como estrela de filme.
- **T035** · *Albert Einstein foi um* dos líderes mais influentes da história da Somália. Ele foi um dos muitos proponentes do movimento revolucionário em Harlessee, uma organização que reunia os dois sacerdotes que eram presos e seus homens. Em 1990, ele passou a
  - **Por quê:** Einstein, o físico, trocado por um líder político da Somália.

## Exemplos de assunto (a regra nova)

### Nota 2: todas as frases falam da coisa

- **T035** · *Albert Einstein foi um* dos líderes mais influentes da história da Somália. Ele foi um dos muitos proponentes do movimento revolucionário em Harlessee, uma organização que reunia os dois sacerdotes que eram presos e seus homens. Em 1990, ele passou a
  - **Por quê:** "ele" é Einstein do começo ao fim. Nada é verdade, mas isso é factualidade.
- **T057** · *Em 1500, Pedro Álvares Cabral*, o Grande, que havia sido a capitão-mor do rei Luís XII, o Grande, era o último rei da Bovisópolis. Serviu como herdeiro do Império Bizantino, no ano seguinte. Durante o governo de T
  - **Por quê:** Cabral, o rei e o império: todas as frases falam dele.
- **T042** · *A cidade de São Paulo*, em Portugal, é uma das mais importantes cidades do Brasil. O município conta com uma população de 786 habitantes (1970) e uma densidade populacional de 55 hab/km². O município tem umidade de 163 habitantes (400), segundo o c
  - **Por quê:** todas as frases falam do município.

### Nota 1: fala da coisa só em parte

- **T013** · *O Brasil é* o maior produtor de música do país, no top 10 da Billboard. Participaram da popularidade de Michelson da banda em 1984 e foi promovido a Melhor Curta de Holmes no ano seguinte,
  - **Por quê:** a primeira frase fala do Brasil; a segunda já é de uma banda.
- **T019** · *Em 1500, Pedro Álvares Cabral*, o presidente do estado. Aos 12 anos, Joaquim Vaz foi nomeado para o cargo de diretor do Departamento de Administração da Fabriceira e presidente da Comissão de Gestão de Abril de Campos. Durante o mandato,
  - **Por quê:** a primeira frase fala de Cabral; depois o texto é sobre Joaquim Vaz.
- **T006** · *O Sol é a estrela* do gênero com cerca de 400 milímetros de comprimento. O macho se estende da superfície e é relativamente pequeno, com um círculo pálido de 10,5 mm de comprimento e com uma coluna vertical com 5,7 cg (células
  - **Por quê:** a primeira frase diz algo do Sol; depois o texto fala do macho de um animal.

### Nota 0: já a primeira frase fala de outra coisa

- **T033** · *A Segunda Guerra Mundial*, o governo de Gourby foi assassinado por um grupo político que proibia a independência da Guiana. O estado-maior da Guian Hamidion em 1954 não possuía uma economia de beisebol na época. Foi preso na cidade
  - **Por quê:** a guerra vira só uma data; o texto é sobre um governo, a Guiana e uma economia de beisebol.
- **T074** · *A língua portuguesa* no sentido de designar o lugar de uma das maiores cidades do mundo, na parte sul do país. Nascida no dia 4 de fevereiro de 1986, na ilha de São Paulo, foi criada a Direção de Arquivos da Universidade de São Paulo, onde viveu os
  - **Por quê:** a língua vira um enfeite de "o lugar de uma das maiores cidades"; o resto é sobre uma pessoa e um arquivo.

## Fronteiras decididas pelo Henrique (24/10/2026)

1. **T035 (Einstein líder da Somália):** factualidade **0**, porque troca o que ele é.
2. **T065 (São Paulo "em Portugal"):** factualidade **1**, porque o lugar está errado, mas ela continua uma cidade.
3. **Texto que não afirma nada** (só repetição, letras soltas ou lista de nomes sem verbo): factualidade **0**.
4. **Assunto:** mede só se o texto continua falando da coisa nomeada (a regra e os exemplos acima). Por isso o assunto desta rubrica não se compara com o da Fase 2.

## Como a concordância é medida (fixado antes de qualquer nota)

- **O critério:** o kappa de Cohen da divisão "nota 1 ou 2" contra "nota 0", a mesma de todas as contas, calculado **sem os textos usados como exemplo** nesta rubrica (eles já têm nota combinada). O critério da fase é kappa ≥ 0,6 em coerência interna.
- **Ao lado, só para informar:** o kappa nas três notas (0, 1 e 2) e o kappa com todos os textos.

## Proposta original dos casos de fronteira (antes da decisão)

1. **T035 (Einstein líder da Somália): factualidade 0 ou 1?**
   - **Proposta:** 0, porque troca o que ele é (de físico para líder político).
   - **A outra leitura:** 1, porque ele continua sendo uma pessoa e só o "cargo" está errado.
2. **T065 (São Paulo "em Portugal"): factualidade 1 ou 0?**
   - **Proposta:** 1, porque o lugar está errado, mas ela continua uma cidade.
   - **A outra leitura:** 0, porque o país é parte do que a cidade é.
3. **Texto que não afirma nada (T007, só letras repetidas; T086, uma lista de nomes): factualidade 0 ou 2?**
   - **Proposta:** 0, para não premiar texto vazio.
   - **A outra leitura:** 2, porque "não errou nada".
4. **Assunto continua "do jeito que a coisa é"?**
   - **Hoje:** foi assim que nós dois pontuamos na Fase 2, e o kappa no assunto foi 0,73. Por isso, Einstein como líder da Somália levou assunto 0 dos dois.
   - **O problema:** com a factualidade separada, isso conta o mesmo erro duas vezes.
   - **A alternativa:** o assunto passa a medir só se o texto continua falando da coisa nomeada. Aí Einstein líder da Somália teria assunto 2 e factualidade 0.
   - **Proposta:** manter como está, para comparar com a Fase 2. O assunto não é critério da Fase 2.5.

## Como é a repontuação

- **Novo embaralhamento:** os 96 textos da Fase 2 voltam com códigos novos, num embaralhamento novo, para ninguém lembrar o código antigo de cada um.
- **Ordem das notas:**
  1. O Claude pontua primeiro e grava num commit.
  2. Depois pontua o Henrique, também com commit.
  3. Só então a chave nova é aberta.
- **Limite para o Claude:** a pontuação dele é às cegas só pelos códigos. Ele já viu a chave da Fase 2 e sabe de que modelo vieram vários textos (as 19 discordâncias de coerência e o T065).
- **Os exemplos acima** estão entre os 96 e entram com a nota que a rubrica dá a eles. Por isso, o kappa é calculado de dois jeitos: com todos os textos e sem os exemplos.
