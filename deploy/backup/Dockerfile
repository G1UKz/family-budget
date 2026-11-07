# pg_dump/pg_restore + restic for the backup and restore-check CronJobs
FROM postgres:17-alpine
RUN apk add --no-cache restic ca-certificates
COPY entrypoint.sh /usr/local/bin/budget-backup
USER 70
ENTRYPOINT ["/usr/local/bin/budget-backup"]
