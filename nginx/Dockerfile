FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY certs/ /etc/nginx/certs/
RUN nginx -t
