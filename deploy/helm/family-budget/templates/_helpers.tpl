{{- define "fb.name" -}}{{ .Release.Name }}{{- end -}}
{{- define "fb.labels" -}}
app.kubernetes.io/name: family-budget
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "fb.selector" -}}
app.kubernetes.io/name: family-budget
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "fb.dbSecret" -}}
{{- if .Values.postgres.cnpg.enabled -}}{{ include "fb.name" . }}-db-app{{- else -}}{{ .Values.postgres.existingUriSecret }}{{- end -}}
{{- end -}}
{{- define "fb.env" -}}
- name: BUDGET_DATABASE_URL
  valueFrom: {secretKeyRef: {name: {{ include "fb.dbSecret" . }}, key: uri}}
- name: BUDGET_SECRET_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretName }}, key: BUDGET_SECRET_KEY}}
- name: BUDGET_ANTHROPIC_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.secretName }}, key: BUDGET_ANTHROPIC_API_KEY, optional: true}}
- name: BUDGET_HOME_CITY_REGEX
  valueFrom: {secretKeyRef: {name: {{ .Values.secretName }}, key: BUDGET_HOME_CITY_REGEX, optional: true}}
- name: BUDGET_ENV
  value: {{ .Values.app.env | quote }}
- name: BUDGET_COOKIE_SECURE
  value: {{ .Values.ingress.tls | quote }}
- name: BUDGET_START_DATE
  value: {{ .Values.app.startDate | quote }}
- name: BUDGET_LLM_MODEL
  value: {{ .Values.app.llmModel | quote }}
{{- end -}}
{{- define "fb.securityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
capabilities: {drop: [ALL]}
{{- end -}}

{{- define "fb.backupPod" -}}
restartPolicy: Never
automountServiceAccountToken: false
securityContext: {runAsUser: 70, runAsGroup: 70, fsGroup: 70, seccompProfile: {type: RuntimeDefault}}
containers:
  - name: job
    image: {{ .Values.backup.image }}
    args: [{{ .mode | quote }}]
    env:
      - name: DATABASE_URI
        valueFrom: {secretKeyRef: {name: {{ include "fb.dbSecret" . }}, key: uri}}
      - name: RESTIC_KEEP
        value: {{ .Values.backup.keep | quote }}
      - name: RESTIC_CACHE_DIR
        value: /work/cache
      - name: TAG
        value: {{ include "fb.name" . }}
    envFrom: [{secretRef: {name: {{ .Values.backup.secretName }}}}]
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities: {drop: [ALL]}
    resources: {requests: {cpu: 20m, memory: 64Mi}, limits: {memory: 512Mi}}
    volumeMounts: [{name: work, mountPath: /work}]
volumes: [{name: work, emptyDir: {}}]
{{- end -}}
