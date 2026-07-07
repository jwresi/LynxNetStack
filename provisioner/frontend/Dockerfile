FROM node:18-alpine AS builder

ARG REACT_APP_API_URL=/provision
ENV REACT_APP_API_URL=$REACT_APP_API_URL

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --only=production || npm install
COPY . .
RUN npm run build

# Production stage — serve with nginx for subpath support
FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
