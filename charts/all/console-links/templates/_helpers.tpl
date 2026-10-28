{{/*
  Application menu icon as a data URI.
  grafana.svg, kafka-console.svg, and workshop-registration.png are the
  official assets from ia-computer-vision charts/all/console-links.
  apicurio.svg is the icon shipped in the Apicurio Registry operator CSV.
  PNG bytes must keep an image/png mediatype or the menu shows a broken image.
*/}}
{{- define "console-links.iconURL" -}}
{{- $file := .icon -}}
{{- $mediatype := "image/svg+xml" -}}
{{- if hasSuffix ".png" $file -}}
{{- $mediatype = "image/png" -}}
{{- end -}}
{{- $data := .root.Files.Get (printf "files/icons/%s" $file) -}}
{{- if hasSuffix ".svg" $file -}}
{{- $data = trim $data -}}
{{- end -}}
data:{{ $mediatype }};base64,{{ $data | b64enc }}
{{- end -}}
