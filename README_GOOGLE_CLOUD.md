# Sistema Experto DJ — despliegue en Google Cloud

`negocio.py` aplica las reglas R01–R27 y propone canciones del catálogo; `datos.py` guarda el conocimiento y los datos del DJ en **PostgreSQL**, y `app.py` sirve la API Flask con inicio de sesión. En Cloud Run, `datos.py` puede leer `reglas.json` desde **Cloud Storage** con la identidad de servicio.

**Base de datos.** La aplicación necesita un PostgreSQL accesible y tres variables: `DATABASE_URL` (con usuario y clave), `SECRET_KEY` (firma la cookie de sesión; debe ser la misma en todas las instancias) y `COOKIE_SEGURA=1`. Lo habitual es Cloud SQL para PostgreSQL, con la URL y la clave guardadas en Secret Manager y entregadas con `--set-secrets`. Los comandos de abajo despliegan el servicio; **la creación de la instancia de Cloud SQL y de los secretos no está incluida ni probada aquí**: siga la guía oficial «Connect from Cloud Run» de Cloud SQL.

## Despliegue desde Cloud Shell

1. Abrir Google Cloud Console > Cloud Shell. Subir `Sistema_Inferencia_Google_Cloud.zip` con el menú de tres puntos > Upload.
2. Ejecutar:

```bash
unzip Sistema_Inferencia_Google_Cloud.zip -d sistema-dj
cd sistema-dj
PROJECT_ID="$(gcloud config get-value project)"
REGION="us-central1"
BUCKET="${PROJECT_ID}-dj-conocimiento"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com iam.googleapis.com
gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" --uniform-bucket-level-access
gcloud storage cp reglas.json "gs://${BUCKET}/reglas.json"
gcloud iam service-accounts create dj-experto-run --display-name="Sistema Experto DJ Cloud Run"
SA="dj-experto-run@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" --role="roles/storage.objectViewer"
gcloud run deploy sistema-experto-dj --source . --region="${REGION}" --allow-unauthenticated --service-account="${SA}" --set-env-vars="GCS_BUCKET=${BUCKET},GCS_OBJECT=reglas.json,COOKIE_SEGURA=1" --set-secrets="DATABASE_URL=dj-database-url:latest,SECRET_KEY=dj-secret-key:latest" --min-instances=0 --max-instances=1 --memory=512Mi
```

Si la primera compilación muestra error de permisos de Cloud Build, consultar el mensaje detallado: puede requerir conceder `roles/run.builder` a la cuenta que Google Cloud Build indique. Nunca otorgar permisos amplios de propietario como solución rápida.

3. Abrir la URL que entrega Cloud Run y consultar `/api/opciones` y `/api/salud`. Probar recomendaciones desde la web.

## Local Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.ejemplo .env      # y edite DATABASE_URL
python3 -m unittest -v
python3 app.py
```

Sin GCS_BUCKET se leen las reglas locales. No establecer GCS_BUCKET en la máquina local a menos que se hayan configurado credenciales de desarrollo para Google Cloud.

## Actualizar reglas en GCS

```bash
gcloud storage cp reglas.json "gs://${BUCKET}/reglas.json"
```

El conocimiento se carga cuando se crea el esquema de la base; subir un `reglas.json` nuevo no cambia una base que ya existe. Hacer copias o versionar el objeto para evitar pérdida accidental.

## Evidencia para la actividad

Capturar Cloud Storage > `reglas.json`; Cloud Run > URL + servicio; navegador con el evento, el contexto, las reglas disparadas y las recomendaciones; Cloud Shell durante despliegue; catálogo de Vertex AI (exploración). No afirmar que Cloud Run es un motor administrado de IA: la inferencia es la implementación Python del estudiante. Si el docente exige consumir un servicio **gestionado de IA**, integrar Vertex AI requiere una ampliación independiente.

## Costos y seguridad

Tener crédito de prueba no implica costo cero. Cloud Run, Cloud Build, Artifact Registry y Storage tienen facturación/retención según la configuración. Configurar alertas en Facturación. El bucket queda privado; el acceso público es solo a la aplicación web. Al finalizar, eliminar servicio Cloud Run, imágenes de Artifact Registry y el bucket para dejar de generar gastos.
