# Formulação e estudo dos algoritmos

## 1. Pergunta do estudo

Como distribuir a água disponível entre períodos para atender à demanda com
menor custo térmico, respeitando os limites do reservatório e das usinas?

A primeira versão utiliza afluências e demandas conhecidas, um reservatório,
produtividade hidrelétrica constante e períodos de mesma duração. Os números
estão em unidades normalizadas compatíveis: `u` e `A` representam quantidades
de água por período, `v` representa armazenamento e `eta*u` representa energia.
`g` e `d` também representam energia por período. Custos são unidades monetárias
do estudo. Não se devem interpretar diretamente os dados como MW e hm³.

## 2. Variáveis e função objetivo

Para cada período `t` e térmica `j`:

- `g[t,j]`: geração térmica;
- `u[t]`: água turbinada;
- `v[t]`: volume armazenado ao fim do período;
- `s[t]`: água vertida.

Minimizar:

```text
sum_t sum_j (a[j] * g[t,j]^2 + b[j] * g[t,j])
```

Com as restrições:

```text
sum_j g[t,j] + eta*u[t] = demanda[t]
v[t] = v[t-1] + afluencia[t] - u[t] - s[t]
0 <= g[t,j] <= capacidade_termica[j]
0 <= u[t] <= capacidade_turbinamento
0 <= v[t] <= capacidade_reservatorio
s[t] >= 0
v[T] >= reserva_final
```

`v[0]` é dado. A reserva final explicita uma exigência ao fim do horizonte;
não equivale a uma função de custo futuro. Não há penalização de vertimento.

## 3. Por que é convexo?

O código exige `a[j] > 0`. A Hessiana tem entradas `2*a[j]` nas posições de
geração térmica e zero nas demais. Portanto, é semidefinida positiva.
Todas as restrições são afins e definem um conjunto convexo.
Assim, um ótimo local é global. A existência de solução depende da viabilidade
dos dados; convexidade não garante que a demanda possa ser atendida.

O custo é estritamente convexo nas gerações térmicas, mas não em todas as
variáveis. Podem existir diferentes trajetórias hidráulicas ótimas; comparar
somente os vetores de decisão pode levar a conclusões erradas.

O formato numérico comum é:

```text
min 0.5*x' H x + c' x
sujeito a lower <= A*x <= upper
```

Igualdades usam limites inferior e superior iguais. A ordenação das variáveis
em cada período é `[g_1, ..., g_J, u, v, s]`.

## 4. Pontos interiores primal-dual

O método separa igualdades `E*x=f` e desigualdades `G*x<=h`. Introduz folgas
positivas `w` e multiplicadores positivos `z`. Resolve progressivamente:

```text
H*x + c + E'*y + G'*z = 0       (estacionariedade)
E*x - f = 0                    (balanços/igualdades)
G*x + w - h = 0                (desigualdades com folgas)
w_i*z_i -> 0                   (complementaridade)
```

Cada iteração resolve um sistema de Newton denso com eliminação de Gauss e
pivoteamento parcial. A matriz reduzida contém `H + G'*diag(z/w)*G`.
O alvo de centralização é `0.1*mu`, com `mu=sum(w_i*z_i)/m`.
O passo usa fração de `0.995` até a fronteira para manter `w,z > 0`.
O ponto inicial pode violar as restrições.

O critério de parada exige que os resíduos primal e de estacionariedade,
em norma infinita, e a complementaridade média sejam menores que a tolerância.
A complementaridade média não é um certificado explícito de diferença de
objetivos de magnitude igual à tolerância. A implementação é de centralização
fixa, sem preditor-corretor ou busca de passo por função de mérito.

## 5. ADMM

Introduz `z=A*x`, com `z` pertencente à caixa `[lower, upper]`.
Com multiplicador não escalado `y`, executa:

```text
(H + rho*A'*A)*x = -c + A'*(rho*z - y)
z = projecao_na_caixa(A*x + y/rho)
y = y + rho*(A*x - z)
```

A projeção usa apenas `min` e `max`. O método mantém `rho` fixo e reutiliza
a fatoração de Cholesky. Os limites explícitos de todas as variáveis tornam
`A'*A` definida positiva neste modelo.

Os resíduos são `r=A*x-z` e `s=rho*A'*(z_novo-z_anterior)`. O critério exige
`max(norm_inf(r), norm_inf(s)) <= tolerancia`. Para o subproblema quadrático
resolvido exatamente, o segundo resíduo também controla a estacionariedade
do iterado atualizado. A coluna de complementaridade fica vazia nos CSVs do ADMM.

Um iterado pode violar os balanços antes da convergência. Não arredonde a
solução antes de verificar as restrições. O parâmetro `rho` e a escala dos
dados afetam a convergência.

## 6. Comparação reproduzível

Os métodos recebem o mesmo QP, com a mesma ordenação e dados. O cronômetro
inclui a preparação interna do método e o registro do histórico; exclui a
montagem do modelo e a escrita de arquivos. O custo de registrar cada iteração
também influencia a medição.

Registre custo, violação das restrições, resíduos de balanço de água e energia,
número de iterações e tempo. Uma iteração de cada algoritmo tem trabalho
diferente: pontos interiores refatora um sistema, enquanto ADMM reutiliza uma
fatoração. Os resíduos de parada também têm definições diferentes; tolerâncias
iguais não equivalem automaticamente à mesma precisão no objetivo.

Experimentos iniciais:

1. Cenário `base`: observar a transferência de água para os períodos de maior demanda.
2. Cenário `dry`: reduzir todas as afluências à metade.
3. Cenário `reserve`: elevar a reserva final de 5 para 8.
4. Repetir o cenário base com `--rho 0.1`, `--rho 1` e `--rho 10`.
5. Comparar tolerâncias `1e-4`, `1e-6` e `1e-8`, sempre verificando convergência.

Para comparar tempos, repetir execuções e relatar mediana, versão do Python e
ambiente. O exemplo pequeno serve para estudar comportamento, sem sustentar
conclusões gerais sobre desempenho dos métodos.

## 7. Validação e limites

Os testes verificam dois casos com solução analítica, atendimento dos balanços,
concordância dos custos entre métodos e aumento do custo nos cenários seco e
de maior reserva. Um teste de demanda impossível verifica que ADMM não declara
convergência no limite de iterações usado.

Os algoritmos não produzem certificados de inviabilidade ou ilimitabilidade.
Pontos interiores pode atingir o limite de iterações ou encontrar um sistema
numericamente singular. Falha de convergência, isoladamente, não prova
inviabilidade. Dados muito mal escalados ou casos degenerados exigem tratamento
adicional. A biblioteca padrão usa ponto flutuante de precisão finita.

Esta etapa não inclui rede elétrica, múltiplos reservatórios, cascatas,
incerteza, cenários, decomposição, custo futuro, déficit de energia ou
produtividade variável. Os sistemas densos destinam-se a instâncias pequenas.

## 8. Roteiro para uma futura postagem

Uma sequência possível é apresentar a decisão de usar ou guardar água,
mostrar as duas equações de balanço e explicar a convexidade. Em seguida,
comparar como cada algoritmo reduz seus resíduos e exibir o mesmo custo final
com as respectivas violações. Encerrar com o efeito da afluência e da reserva
final, indicando as simplificações e disponibilizando o código reproduzível.

Gráficos futuros podem mostrar geração por período, armazenamento e resíduos
em escala logarítmica. Os CSVs já permitem construir essas figuras sem acoplar
uma biblioteca gráfica ao núcleo do projeto.
