FROM nginx:alpine

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/arbitrage.conf

# Create SSL directory
RUN mkdir -p /etc/nginx/ssl

EXPOSE 80 443
