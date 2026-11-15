# A ideia original

> Esse é um dia inteiro da minha fábrica de vídeos com IA, e quase tudo acontece sem eu encostar.
>
> De madrugada, o maestro já montou a agenda. Cada canal com o vídeo do dia, cada um no seu horário. Às cinco e meia, sai o primeiro.
>
> O agente da sala vai até a estante e pesquisa o tema. Senta e escreve o roteiro. Entra na cabine e grava a narração. Desenha as cenas no quadro, monta o vídeo no computador e ainda faz a thumbnail.
>
> Se a IA trava ou bate no limite do dia, ele espera e retoma sozinho de onde parou.
>
> Quando fica pronto, o vídeo chega pra mim com os shorts, as thumbnails e as opções de título. Eu escolho o horário e aprovo. Ele sobe sozinho, agendado.
>
> E enquanto isso, eu tô na rua, cuidando das minhas lojas e fazendo missão. Cada vídeo que a fábrica faz vira despesa da empresa no jogo, e cada view vira moeda.
>
> À noite, o dia seguinte já tá na agenda, e o escritório não para. Não é só um jogo, é criar conteúdo e monetizar enquanto se diverte.

## Leitura da ideia em requisitos

| Trecho | Requisito |
|---|---|
| "o maestro já montou a agenda… cada canal… cada um no seu horário" | Agendador multicanal com horário de início por canal; agenda do dia seguinte pronta à noite. |
| "pesquisa… roteiro… narração… cenas… monta… thumbnail" | Pipeline sequencial de 6 etapas, cada uma com seu provedor de IA. |
| "se a IA trava ou bate no limite do dia, espera e retoma de onde parou" | Checkpoint por etapa, pausa com horário de retomada, retentativas. |
| "chega pra mim com shorts, thumbnails e opções de título" | Pacote de aprovação: vídeo + shorts + N thumbnails + N títulos. |
| "escolho o horário e aprovo. Sobe sozinho, agendado" | Aprovação em um passo e publicação agendada automática. |
| "cada vídeo vira despesa… cada view vira moeda" | Camada de jogo: custo de produção → despesa; views → moeda. |
| "eu tô na rua, cuidando das lojas e fazendo missão" | Experiência mobile-first; o dono interage pouco e de qualquer lugar. |
