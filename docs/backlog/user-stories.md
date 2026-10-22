# Navby — Historias de Usuario

> Describen **comportamiento** observable por el usuario, sin decisiones de diseño. Cada historia tiene al menos dos escenarios en Gherkin. Las reglas citadas (`RN-xx`, `RL-xx`) están en [navby-documentation.md](../navby-documentation.md) y las historias técnicas que las implementan, en [technical-stories.md](technical-stories.md).

## Mapa de épicas

| Épica | Historias |
| :--- | :--- |
| EP01 · Cuenta y acceso | US-01 a US-10 |
| EP02 · Búsqueda y recomendación | US-11 a US-19 y US-34 |
| EP03 · Preferencias | US-20 y US-21 |
| EP04 · Itinerarios guardados | US-22 a US-24 |
| EP05 · Créditos y pagos | US-25 a US-30 |
| EP06 · Protección al consumidor | US-31 |
| EP07 · Sitio público | US-32 y US-33 |

**Actores:** *visitante* (sin cuenta), *viajero* (con cuenta y correo verificado).

---

## EP01 · Cuenta y acceso

### US-01 · Crear una cuenta con correo

**Como** visitante **quiero** crear una cuenta con mi correo y una contraseña **para** recibir búsquedas gratuitas cada día.

Reglas: RN-17, RL-01 · Técnica: TS-01

```gherkin
Escenario: Registro exitoso
  Dado que el visitante no tiene cuenta con "ana@mail.com"
  Cuando se registra con ese correo, su nombre, una contraseña válida y acepta los Términos y la Política de Privacidad
  Entonces la cuenta queda creada pendiente de verificación
  Y recibe en su correo un código de 6 dígitos

Escenario: Registro sin aceptar los términos
  Dado que el visitante completa sus datos
  Cuando intenta registrarse sin aceptar los Términos y la Política de Privacidad
  Entonces el registro no se completa
  Y se le indica que debe aceptarlos

Escenario: Correo ya registrado
  Dado que ya existe una cuenta con "ana@mail.com"
  Cuando el visitante intenta registrarse con ese correo
  Entonces el registro no se completa
  Y se le indica que el correo ya está registrado

Escenario: Correo desechable
  Dado que el visitante usa un correo de un servicio temporal
  Cuando intenta registrarse
  Entonces el registro no se completa
  Y se le pide usar un correo permanente
```

### US-02 · Verificar el correo

**Como** visitante recién registrado **quiero** confirmar mi correo con el código recibido **para** activar mi cuenta y mis créditos gratuitos.

Reglas: RN-12, RN-17 · Técnica: TS-02

```gherkin
Escenario: Código correcto
  Dado que el visitante recibió el código "849201" hace menos de 10 minutos
  Cuando ingresa ese código
  Entonces su correo queda verificado
  Y su sesión queda iniciada
  Y dispone de 10 créditos gratuitos

Escenario: Código incorrecto
  Dado que el visitante tiene un código vigente
  Cuando ingresa un código distinto
  Entonces la verificación no se completa
  Y puede volver a intentarlo

Escenario: Demasiados intentos
  Dado que el visitante falló 5 veces con su código
  Cuando intenta verificar otra vez
  Entonces se le indica que debe pedir un código nuevo

Escenario: Código vencido
  Dado que el código se envió hace más de 10 minutos
  Cuando el visitante lo ingresa
  Entonces la verificación no se completa
  Y se le sugiere pedir un código nuevo
```

### US-03 · Pedir un nuevo código

**Como** visitante sin verificar **quiero** pedir otro código **para** completar la verificación si el primero no llegó o venció.

Técnica: TS-03

```gherkin
Escenario: Reenvío permitido
  Dado que el visitante no pidió un código en el último minuto
  Cuando solicita un nuevo código
  Entonces recibe un código nuevo
  Y el código anterior deja de funcionar

Escenario: Reenvío demasiado seguido
  Dado que el visitante pidió un código hace 20 segundos
  Cuando solicita otro
  Entonces no se envía un nuevo código
  Y se le indica que espere un momento

Escenario: Correo desconocido
  Dado que no existe una cuenta con "nadie@mail.com"
  Cuando alguien solicita un código para ese correo
  Entonces recibe la misma confirmación genérica que cualquier otra solicitud
```

### US-04 · Iniciar sesión con correo y contraseña

**Como** viajero **quiero** iniciar sesión con mi correo y contraseña **para** acceder a mis créditos y búsquedas.

Técnica: TS-04

```gherkin
Escenario: Credenciales correctas
  Dado que el viajero tiene una cuenta verificada
  Cuando inicia sesión con su correo y contraseña
  Entonces su sesión queda iniciada

Escenario: Credenciales incorrectas
  Dado que el viajero escribe mal su contraseña
  Cuando intenta iniciar sesión
  Entonces la sesión no se inicia
  Y se le indica que el correo o la contraseña no son correctos, sin precisar cuál

Escenario: Correo sin verificar
  Dado que la cuenta existe pero su correo no está verificado
  Cuando intenta iniciar sesión
  Entonces la sesión no se inicia
  Y se le pide verificar su correo
```

### US-05 · Entrar con Google

**Como** visitante o viajero **quiero** entrar con mi cuenta de Google **para** no tener que crear ni recordar una contraseña.

Reglas: RL-01 · Técnica: TS-05

```gherkin
Escenario: Primera vez con Google
  Dado que no existe una cuenta con el correo de Google del visitante
  Cuando entra con Google y acepta los Términos y la Política de Privacidad
  Entonces se crea su cuenta con el correo ya verificado
  Y dispone de 10 créditos gratuitos

Escenario: Cuenta existente con el mismo correo verificado
  Dado que el viajero ya tiene una cuenta verificada con contraseña y el mismo correo
  Cuando entra con Google
  Entonces entra a su cuenta existente
  Y conserva sus créditos e itinerarios

Escenario: Alguien registró antes su correo sin verificarlo
  Dado que existe una cuenta sin verificar con el correo de Google del visitante
  Cuando el visitante entra con Google
  Entonces la cuenta queda bajo su control y verificada
  Y la contraseña que había creado otra persona deja de servir
```

### US-06 · Mantener la sesión abierta

**Como** viajero **quiero** que mi sesión siga activa mientras uso Navby **para** no tener que iniciar sesión a cada rato.

Técnica: TS-06

```gherkin
Escenario: Sesión renovada sin intervención
  Dado que el viajero inició sesión hace 3 días
  Cuando vuelve a Navby
  Entonces sigue con la sesión iniciada

Escenario: Sesión vencida
  Dado que el viajero no usa Navby desde hace más de 7 días
  Cuando vuelve
  Entonces debe iniciar sesión de nuevo

Escenario: Varias pestañas abiertas
  Dado que el viajero tiene Navby abierto en dos pestañas
  Cuando ambas renuevan la sesión al mismo tiempo
  Entonces ambas siguen funcionando sin cerrar la sesión
```

### US-07 · Cerrar sesión

**Como** viajero **quiero** cerrar mi sesión **para** que nadie más use mi cuenta en ese dispositivo.

Técnica: TS-07

```gherkin
Escenario: Cierre de sesión
  Dado que el viajero tiene la sesión iniciada
  Cuando cierra sesión
  Entonces su sesión termina en ese dispositivo
  Y para volver a cotizar debe iniciar sesión

Escenario: Otros dispositivos no se afectan
  Dado que el viajero tiene sesión en su laptop y en su celular
  Cuando cierra sesión en la laptop
  Entonces sigue con la sesión iniciada en el celular
```

### US-08 · Recuperar la contraseña

**Como** viajero **quiero** definir una contraseña nueva si olvidé la actual **para** recuperar el acceso a mi cuenta.

Técnica: TS-08, TS-09

```gherkin
Escenario: Recuperación exitosa
  Dado que el viajero solicitó recuperar su contraseña
  Y recibió un enlace hace menos de 30 minutos
  Cuando define una contraseña nueva válida con ese enlace
  Entonces puede iniciar sesión con la nueva contraseña
  Y se cierran sus sesiones en todos los dispositivos

Escenario: Enlace vencido o ya usado
  Dado que el enlace tiene más de 30 minutos o ya se usó
  Cuando el viajero intenta definir una contraseña nueva
  Entonces el cambio no se realiza
  Y se le sugiere solicitar otro enlace

Escenario: Correo desconocido
  Dado que no existe una cuenta con el correo indicado
  Cuando alguien solicita recuperar la contraseña
  Entonces recibe la misma confirmación genérica que cualquier otra solicitud
```

### US-09 · Ver mi perfil

**Como** viajero **quiero** ver los datos de mi cuenta **para** saber con qué correo y métodos de acceso estoy registrado.

Técnica: TS-10

```gherkin
Escenario: Cuenta con contraseña y Google
  Dado que el viajero se registró con contraseña y luego entró con Google
  Cuando consulta su perfil
  Entonces ve su nombre, su correo y que tiene ambos métodos de acceso

Escenario: Sin sesión
  Dado que el visitante no inició sesión
  Cuando intenta consultar un perfil
  Entonces se le pide iniciar sesión
```

### US-10 · Eliminar mi cuenta

**Como** viajero **quiero** eliminar mi cuenta **para** que Navby deje de tratar mis datos personales.

Reglas: RL-02 · Técnica: TS-11

```gherkin
Escenario: Eliminación confirmada
  Dado que el viajero tiene itinerarios guardados y créditos
  Cuando confirma la eliminación escribiendo "ELIMINAR"
  Entonces su nombre y correo dejan de estar asociados a la cuenta
  Y sus itinerarios y créditos se eliminan
  Y su sesión se cierra en todos los dispositivos

Escenario: Confirmación incorrecta
  Dado que el viajero escribe una confirmación distinta de "ELIMINAR"
  Cuando intenta eliminar su cuenta
  Entonces la cuenta no se elimina

Escenario: Volver a registrarse
  Dado que el viajero eliminó su cuenta
  Cuando se registra de nuevo con el mismo correo
  Entonces obtiene una cuenta nueva, sin los datos anteriores
```

---

## EP02 · Búsqueda y recomendación

### US-11 · Encontrar mi ciudad al escribirla

**Como** visitante **quiero** encontrar ciudades escribiendo su nombre en español o en inglés **para** elegir el origen y el destino sin conocer códigos de aeropuerto.

Reglas: RN-06 · Técnica: TS-12

```gherkin
Escenario: Nombre en español
  Cuando el visitante escribe "Tok"
  Entonces entre las sugerencias aparece "Tokio, Japón"

Escenario: Nombre en inglés o código
  Cuando el visitante escribe "Lond" o "LHR"
  Entonces entre las sugerencias aparece "Londres, Reino Unido"

Escenario: Sin tildes ni mayúsculas
  Cuando el visitante escribe "bogota"
  Entonces entre las sugerencias aparece "Bogotá, Colombia"

Escenario: Texto demasiado corto
  Cuando el visitante escribe una sola letra
  Entonces no se muestran sugerencias todavía
```

### US-12 · Ver la ruta posible antes de las tarifas

**Como** visitante **quiero** ver de inmediato si existe una ruta entre dos ciudades y por dónde pasaría **para** no esperar en vano si el viaje no es posible.

Reglas: RN-05, RN-07, RN-12 · Técnica: TS-13

```gherkin
Escenario: Ruta posible
  Dado que el visitante eligió Lima como origen y Tokio como destino
  Cuando inicia la búsqueda
  Entonces ve en segundos una ruta preliminar con las ciudades donde haría escala
  Y el tiempo mínimo estimado del viaje

Escenario: Ruta imposible
  Dado que no existe forma de unir las dos ciudades con 2 escalas o menos
  Cuando inicia la búsqueda
  Entonces se le informa que no hay rutas posibles
  Y no se le cobra ningún crédito

Escenario: Sin cuenta
  Dado que el visitante no inició sesión
  Cuando inicia la búsqueda
  Entonces igual ve la ruta preliminar
  Y se le pide iniciar sesión para ver las tarifas
```

### US-13 · Recibir las 3 mejores recomendaciones

**Como** viajero **quiero** recibir las 3 opciones de vuelo con mejor equilibrio entre precio, duración y escalas **para** decidir rápido sin comparar decenas de resultados.

Reglas: RN-01 a RN-05, RN-08, RN-12 · Técnica: TS-14, TS-27, TS-28

```gherkin
Escenario: Podio de una búsqueda solo ida
  Dado que el viajero tiene 10 créditos
  Cuando busca vuelos de Lima a Madrid para el 1 de noviembre para 1 adulto en económica
  Entonces recibe hasta 3 recomendaciones ordenadas de mejor a peor
  Y cada una muestra precio total, duración, escalas, aerolíneas, su afinidad y cuánto supera el tiempo mínimo físico
  Y se descuentan 5 créditos

Escenario: Ida y vuelta
  Dado que el viajero busca de Lima a Madrid con salida el 1 y regreso el 15 de noviembre
  Cuando recibe las recomendaciones
  Entonces cada una incluye el vuelo de ida y el de regreso
  Y el precio y la duración corresponden al viaje completo

Escenario: Sin categorías aisladas
  Cuando el viajero recibe sus recomendaciones
  Entonces ninguna se presenta como "la más barata" o "la más rápida"
  Y el orden refleja un único puntaje combinado

Escenario: Comprar una recomendación
  Dado que el viajero eligió una recomendación
  Cuando decide comprarla
  Entonces es llevado al sitio de la aerolínea o agencia que la vende
```

### US-14 · Buscar entre ciudades con varios aeropuertos

**Como** viajero **quiero** buscar por ciudad aunque tenga varios aeropuertos **para** no tener que saber cuál me conviene.

Reglas: RN-06, RN-14 · Técnica: TS-13, TS-14

```gherkin
Escenario: Todos los aeropuertos por defecto
  Dado que el viajero busca de Lima a Tokio
  Cuando recibe las recomendaciones
  Entonces pueden incluir vuelos que llegan a Haneda o a Narita
  Y el costo sigue siendo de 5 créditos

Escenario: Excluir un aeropuerto
  Dado que el viajero desmarca Narita
  Cuando busca de Lima a Tokio
  Entonces todas las recomendaciones llegan a Haneda

Escenario: Ciudad con muchos aeropuertos
  Dado que el viajero busca de Londres a Lima
  Cuando recibe las recomendaciones
  Entonces Navby consultó solo los aeropuertos de Londres con mejores conexiones
  Y el viajero no tuvo que elegir ninguno
```

### US-15 · No pagar si no hay vuelos o falla el proveedor

**Como** viajero **quiero** que no se me cobre cuando no recibo recomendaciones **para** pagar solo por resultados útiles.

Reglas: RN-07, RN-09 · Técnica: TS-14

```gherkin
Escenario: No hay vuelos para la fecha
  Dado que la ruta existe pero ninguna aerolínea vende vuelos para esa fecha
  Cuando el viajero busca
  Entonces se le informa que no hay vuelos disponibles
  Y sus créditos quedan igual que antes de buscar

Escenario: El proveedor de tarifas no responde
  Dado que el proveedor de tarifas no responde
  Cuando el viajero busca
  Entonces se le informa que no fue posible consultar precios
  Y sus créditos quedan igual que antes de buscar

Escenario: Falla solo uno de los aeropuertos
  Dado que el viajero busca hacia una ciudad con dos aeropuertos
  Y el proveedor responde solo para uno de ellos
  Cuando recibe las recomendaciones
  Entonces se le avisa que algunos aeropuertos no respondieron
  Y se descuentan los 5 créditos
```

### US-16 · Repetir una búsqueda reciente sin costo

**Como** viajero **quiero** que una búsqueda idéntica a una reciente no me cueste **para** poder volver a ver resultados sin gastar créditos.

Reglas: RN-08, RN-10 · Técnica: TS-14

```gherkin
Escenario: Búsqueda repetida dentro de 30 minutos
  Dado que hace 10 minutos alguien buscó Lima a Madrid con los mismos datos
  Cuando el viajero hace esa misma búsqueda
  Entonces recibe sus recomendaciones
  Y no se le descuenta ningún crédito

Escenario: Búsqueda repetida después de 30 minutos
  Dado que la búsqueda idéntica ocurrió hace 40 minutos
  Cuando el viajero la repite
  Entonces recibe recomendaciones actualizadas
  Y se descuentan 5 créditos
```

### US-17 · Saber que no tengo créditos suficientes

**Como** viajero **quiero** saber cuándo no me alcanzan los créditos **para** decidir si espero la recarga diaria o compro un paquete.

Reglas: RN-08 · Técnica: TS-14

```gherkin
Escenario: Saldo insuficiente
  Dado que el viajero tiene 3 créditos
  Cuando busca una ruta que no está en caché
  Entonces la búsqueda no se realiza
  Y se le ofrece comprar un paquete o esperar la recarga diaria

Escenario: Saldo insuficiente pero resultado reciente
  Dado que el viajero tiene 0 créditos
  Y la misma búsqueda se hizo hace 5 minutos
  Cuando busca
  Entonces recibe las recomendaciones sin costo
```

### US-18 · Evitar cobros dobles

**Como** viajero **quiero** que repetir la orden de búsqueda por error no me cobre dos veces **para** no perder créditos.

Reglas: RN-15 · Técnica: TS-14

```gherkin
Escenario: Doble envío accidental
  Dado que el viajero inició una búsqueda que aún está en curso
  Cuando vuelve a enviarla
  Entonces la primera sigue su curso
  Y la segunda se rechaza informando que ya hay una búsqueda en curso
  Y se descuentan 5 créditos una sola vez

Escenario: Nueva búsqueda al terminar la anterior
  Dado que la búsqueda anterior ya terminó
  Cuando el viajero busca otra ruta
  Entonces la nueva búsqueda se procesa normalmente
```

### US-19 · Volver a ver los resultados de mi búsqueda

**Como** viajero **quiero** volver a consultar las recomendaciones de mi última búsqueda **para** no tener que buscar otra vez.

Reglas: RN-10 · Técnica: TS-16

```gherkin
Escenario: Búsqueda vigente
  Dado que el viajero buscó hace 10 minutos
  Cuando vuelve a consultar esa búsqueda
  Entonces ve las mismas recomendaciones sin costo

Escenario: Búsqueda vencida
  Dado que la búsqueda ocurrió hace más de 30 minutos
  Cuando el viajero intenta verla de nuevo
  Entonces se le indica que los resultados vencieron y debe buscar otra vez

Escenario: Búsqueda de otra persona
  Dado que el viajero conoce el identificador de una búsqueda ajena
  Cuando intenta verla
  Entonces no puede acceder a ella
```

### US-34 · Indicar los datos de mi viaje

**Como** viajero **quiero** indicar el tipo de viaje, las fechas, los pasajeros, la cabina y la moneda **para** recibir recomendaciones que correspondan a mi viaje real.

Reglas: RN-01 a RN-04 · Técnica: TS-14

```gherkin
Escenario: Viaje familiar en ejecutiva
  Dado que el viajero busca ida y vuelta para 2 adultos, 1 niño y 1 infante en cabina ejecutiva con precios en soles
  Cuando recibe las recomendaciones
  Entonces todas corresponden a esa cabina
  Y el precio total incluye a los 4 pasajeros y está en soles

Escenario: Más infantes que adultos
  Cuando el viajero indica 1 adulto y 2 infantes
  Entonces la búsqueda no se realiza
  Y se le indica que cada infante debe viajar con un adulto

Escenario: Más de 9 pasajeros
  Cuando el viajero indica 8 adultos y 2 niños
  Entonces la búsqueda no se realiza
  Y se le indica que el máximo es 9 pasajeros

Escenario: Fechas inválidas
  Cuando el viajero indica una salida anterior a hoy, un regreso anterior a la salida o una salida a más de 330 días
  Entonces la búsqueda no se realiza
  Y se le indica qué fecha corregir
  Y no se le cobra ningún crédito
```

---

## EP03 · Preferencias

### US-20 · Elegir qué me importa más

**Como** viajero **quiero** elegir entre Equilibrado, Ahorro o Rapidez **para** que las recomendaciones reflejen mi prioridad.

Reglas: RN-11, sección 5.4 · Técnica: TS-15

```gherkin
Escenario: Cambiar a Ahorro
  Dado que el viajero recibió recomendaciones con el perfil Equilibrado
  Cuando elige el perfil Ahorro
  Entonces las recomendaciones se reordenan dando más peso al precio
  Y no se descuenta ningún crédito

Escenario: Perfil por defecto
  Dado que el viajero no eligió ningún perfil
  Cuando busca
  Entonces las recomendaciones usan el perfil Equilibrado

Escenario: Búsqueda vencida
  Dado que la búsqueda tiene más de 30 minutos
  Cuando el viajero cambia de perfil
  Entonces se le indica que debe buscar de nuevo
```

### US-21 · Definir mis propios pesos

**Como** viajero **quiero** definir cuánto me importa el precio, la duración y las escalas **para** ajustar las recomendaciones a mi caso.

Reglas: RN-11, sección 5.4 · Técnica: TS-15

```gherkin
Escenario: Pesos válidos
  Dado que el viajero tiene una búsqueda vigente
  Cuando define 40% precio, 40% duración y 20% escalas
  Entonces las recomendaciones se reordenan con esos pesos
  Y no se descuenta ningún crédito

Escenario: Pesos que no suman 100%
  Cuando el viajero define 50% precio, 40% duración y 20% escalas
  Entonces las recomendaciones no cambian
  Y se le indica que los pesos deben sumar 100%

Escenario: Búsqueda vencida
  Dado que la búsqueda tiene más de 30 minutos
  Cuando el viajero define pesos propios
  Entonces las recomendaciones no se recalculan
  Y se le indica que debe buscar de nuevo
```

---

## EP04 · Itinerarios guardados

### US-22 · Guardar una recomendación

**Como** viajero **quiero** guardar una recomendación **para** revisarla más tarde aunque los resultados hayan vencido.

Reglas: RN-13, RL-03 · Técnica: TS-29

```gherkin
Escenario: Guardar dentro de los 30 minutos
  Dado que el viajero tiene una búsqueda vigente
  Cuando guarda la recomendación número 2
  Entonces queda en sus itinerarios con el nombre "LIM → MAD · 2026-11-01"
  Y guardar no le descuenta créditos

Escenario: Guardar dos veces la misma
  Dado que el viajero ya guardó esa recomendación
  Cuando la guarda de nuevo
  Entonces no se crea un duplicado

Escenario: Límite alcanzado
  Dado que el viajero ya tiene 50 itinerarios
  Cuando intenta guardar otro
  Entonces no se guarda
  Y se le sugiere eliminar alguno

Escenario: Búsqueda vencida
  Dado que la búsqueda tiene más de 30 minutos
  Cuando el viajero intenta guardar una recomendación
  Entonces no se guarda
  Y se le indica que debe buscar de nuevo
```

### US-23 · Consultar mis itinerarios

**Como** viajero **quiero** ver mis itinerarios guardados **para** retomar la decisión de compra.

Reglas: RL-03 · Técnica: TS-30, TS-31

```gherkin
Escenario: Lista de itinerarios
  Dado que el viajero guardó 3 itinerarios
  Cuando consulta sus itinerarios
  Entonces ve los 3, del más reciente al más antiguo

Escenario: Detalle con precio histórico
  Dado que el viajero guardó un itinerario hace 5 días
  Cuando abre su detalle
  Entonces ve el precio de ese momento
  Y un aviso de que el precio puede haber cambiado

Escenario: Itinerario de otra persona
  Dado que existe un itinerario de otro usuario
  Cuando el viajero intenta abrirlo
  Entonces se le indica que no existe
```

### US-24 · Eliminar un itinerario

**Como** viajero **quiero** eliminar un itinerario que ya no me interesa **para** mantener mi lista ordenada y liberar espacio.

Técnica: TS-32

```gherkin
Escenario: Eliminación
  Dado que el viajero tiene 50 itinerarios
  Cuando elimina uno
  Entonces deja de aparecer en su lista
  Y puede volver a guardar otro

Escenario: Itinerario inexistente
  Cuando el viajero intenta eliminar un itinerario que no existe o no es suyo
  Entonces se le indica que no existe
```

---

## EP05 · Créditos y pagos

### US-25 · Recibir créditos gratis cada día

**Como** viajero **quiero** recibir 10 créditos gratis cada día **para** hacer 2 búsquedas diarias sin pagar.

Reglas: sección 7 · Técnica: TS-14, TS-17

```gherkin
Escenario: Recarga diaria
  Dado que el viajero gastó sus 10 créditos gratuitos el lunes
  Cuando consulta su saldo el martes después de la medianoche de Lima
  Entonces tiene 10 créditos gratuitos

Escenario: No se acumulan
  Dado que el viajero no usó sus créditos gratuitos el lunes
  Cuando consulta su saldo el martes
  Entonces tiene 10 créditos gratuitos, no 20

Escenario: Se gastan primero los gratuitos
  Dado que el viajero tiene 10 créditos gratuitos y 50 comprados
  Cuando hace una búsqueda
  Entonces le quedan 5 gratuitos y 50 comprados
```

### US-26 · Consultar mi saldo

**Como** viajero **quiero** saber cuántos créditos tengo y cuándo se renuevan **para** planificar mis búsquedas.

Técnica: TS-17

```gherkin
Escenario: Saldo con créditos comprados
  Dado que el viajero tiene 5 créditos gratuitos y 45 comprados
  Cuando consulta su saldo
  Entonces ve 50 créditos, equivalentes a 10 búsquedas
  Y la hora de la próxima recarga gratuita

Escenario: Usuario recién verificado
  Dado que el viajero acaba de verificar su correo
  Cuando consulta su saldo
  Entonces ve 10 créditos gratuitos
```

### US-27 · Ver el historial de créditos

**Como** viajero **quiero** ver en qué usé mis créditos **para** entender mi saldo.

Técnica: TS-18

```gherkin
Escenario: Historial con búsquedas y compras
  Dado que el viajero compró un paquete e hizo 3 búsquedas
  Cuando consulta su historial
  Entonces ve la compra y los 3 descuentos, del más reciente al más antiguo

Escenario: Búsqueda reembolsada
  Dado que una búsqueda falló y se le devolvieron los créditos
  Cuando consulta su historial
  Entonces ve el descuento y la devolución de esa búsqueda
```

### US-28 · Ver los paquetes de créditos

**Como** visitante **quiero** conocer los paquetes y sus precios **para** decidir si me conviene comprar.

Reglas: sección 7 · Técnica: TS-19

```gherkin
Escenario: Catálogo
  Cuando el visitante consulta los paquetes
  Entonces ve Escapada (50 créditos, S/ 9.90), Viajero Frecuente (100, S/ 16.90) y Nómada (250, S/ 34.90)
  Y cuántas búsquedas equivale cada uno

Escenario: Referencia en dólares
  Cuando el visitante consulta los paquetes
  Entonces ve el equivalente aproximado en USD
  Y se le aclara que el cobro se hace en soles
```

### US-29 · Comprar un paquete

**Como** viajero **quiero** comprar un paquete de créditos con Mercado Pago **para** seguir buscando después de mis créditos gratuitos.

Reglas: sección 7 · Técnica: TS-20, TS-22

```gherkin
Escenario: Pago aprobado
  Dado que el viajero elige el paquete Viajero Frecuente
  Cuando paga S/ 16.90 en Mercado Pago y el pago se aprueba
  Entonces recibe 100 créditos comprados
  Y esos créditos no vencen

Escenario: Pago rechazado
  Dado que el viajero intenta pagar el paquete
  Cuando Mercado Pago rechaza el pago
  Entonces no recibe créditos
  Y puede intentar de nuevo

Escenario: Pago abandonado
  Dado que el viajero inició una compra y no pagó
  Cuando pasan 24 horas
  Entonces la compra queda vencida y no recibe créditos

Escenario: Pago confirmado tarde
  Dado que el viajero pagó con un medio que se confirma horas después
  Cuando Mercado Pago confirma el pago
  Entonces recibe sus créditos aunque ya haya cerrado Navby
```

### US-30 · Conocer el resultado de mi pago

**Como** viajero **quiero** saber si mi pago fue aprobado al volver de Mercado Pago **para** saber si ya puedo usar mis créditos.

Técnica: TS-21

```gherkin
Escenario: Pago ya confirmado
  Dado que el viajero regresa de Mercado Pago con el pago aprobado
  Cuando consulta el estado de su compra
  Entonces ve que fue aprobada y su nuevo saldo

Escenario: Pago aún pendiente
  Dado que Mercado Pago todavía no confirma el pago
  Cuando el viajero consulta el estado
  Entonces ve que está pendiente
  Y el estado se actualiza solo cuando llega la confirmación
```

---

## EP06 · Protección al consumidor

### US-31 · Saber que el precio es referencial

**Como** viajero **quiero** saber que el precio mostrado se confirma en el sitio del vendedor **para** no llevarme sorpresas al comprar.

Reglas: RL-03 · Técnica: TS-14, TS-31

```gherkin
Escenario: Aviso en las recomendaciones
  Cuando el viajero recibe recomendaciones
  Entonces cada precio va acompañado del aviso de precio referencial

Escenario: Aviso en itinerarios guardados
  Cuando el viajero abre un itinerario guardado
  Entonces ve la fecha en que se obtuvo el precio
  Y el aviso de que puede haber cambiado
```

---

## EP07 · Sitio público

### US-32 · Entender qué hace Navby

**Como** visitante **quiero** entender en pocos segundos qué hace Navby **para** decidir si lo pruebo.

Técnica: website (repositorio propio, fuera de este backlog)

```gherkin
Escenario: Propuesta de valor
  Cuando el visitante entra al sitio
  Entonces entiende que Navby recomienda 3 vuelos combinando precio, duración y escalas
  Y puede ir directamente a buscar vuelos

Escenario: Idioma
  Dado que el navegador del visitante está en inglés
  Cuando entra al sitio
  Entonces ve el contenido en inglés
  Y puede cambiar a español
```

### US-33 · Consultar los términos y la privacidad

**Como** visitante **quiero** leer los Términos y la Política de Privacidad **para** saber qué acepto al registrarme.

Reglas: RL-01, RL-02 · Técnica: website (repositorio propio, fuera de este backlog)

```gherkin
Escenario: Versión vigente
  Cuando el visitante abre los Términos
  Entonces ve su versión y fecha
  Y es la misma versión que acepta al registrarse

Escenario: Cómo eliminar mis datos
  Cuando el visitante lee la Política de Privacidad
  Entonces encuentra cómo eliminar su cuenta y sus datos
```
