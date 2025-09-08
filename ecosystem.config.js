module.exports = {
  apps: [
    {
      name: "crawl-VPTW",
      script: "sh",
      args: "./scripts/start-api.sh",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      namespace: "crawl.vptw",
    },
  ],
};
