#!/bin/bash

MYSQL_CMD="/root/projects/mysql-5.7.42/build/debug_build/bin/mysql -u root --socket=/root/projects/mysql-5.7.42/build/debug_build/run/mysql.socket"
DB_NAME="test"
TABLE_NAME="t1"

# check the status of database
echo "Checking for database '${DB_NAME}'..."
DB_EXISTS=$($MYSQL_CMD -e "SHOW DATABASES LIKE '${DB_NAME}';" | grep "${DB_NAME}")
if [ -z "$DB_EXISTS" ]; then
    echo "Database '${DB_NAME}' does not exist. Creating..."
    $MYSQL_CMD -e "CREATE DATABASE ${DB_NAME};"
else
    echo "Database '${DB_NAME}' already exists."
fi

# check the status of table
echo "Checking for table '${TABLE_NAME}' in database '${DB_NAME}'..."
TABLE_EXISTS=$($MYSQL_CMD -e "USE ${DB_NAME}; SHOW TABLES LIKE '${TABLE_NAME}';" | grep "${TABLE_NAME}")
if [ -z "$TABLE_EXISTS" ]; then
    echo "Table '${TABLE_NAME}' does not exist. Creating..."
    $MYSQL_CMD -e "USE ${DB_NAME}; CREATE TABLE ${TABLE_NAME} (i INT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY, c CHAR(32) NOT NULL DEFAULT 'dummy_text') ENGINE=InnoDB;"
else
    echo "Table '${TABLE_NAME}' already exists."
fi

# check the status of table t1's data
echo "Checking if table '${TABLE_NAME}' is empty..."
ROW_COUNT=$($MYSQL_CMD -e "USE ${DB_NAME}; SELECT COUNT(*) FROM ${TABLE_NAME};" | tail -n 1)
if [ "$ROW_COUNT" -eq 0 ]; then
    echo "Table '${TABLE_NAME}' is empty. Inserting data..."
    for i in $(seq 1 100); do
        $MYSQL_CMD -e "
        USE ${DB_NAME};
        INSERT INTO ${TABLE_NAME} (i, c) VALUES ($i, 'dummy_text');"
    done
else
    echo "Table '${TABLE_NAME}' is not empty. Skipping data insertion."
fi

echo "Starting two parallel transactions..."

(
    # transaction 1
    $MYSQL_CMD -e "
    USE ${DB_NAME};
    START TRANSACTION;
    SELECT * FROM ${TABLE_NAME} LIMIT 10;
    COMMIT;"
) &

(
    # transaction 2
    echo "Start alter transaction"
    sleep 1  
    $MYSQL_CMD -e "
    USE ${DB_NAME};
    START TRANSACTION;
    ALTER TABLE ${TABLE_NAME} ADD KEY k2(c);"
) &

wait

# delete table t1
echo "Deleting table '${TABLE_NAME}' from database '${DB_NAME}'..."
$MYSQL_CMD -e "USE ${DB_NAME}; DROP TABLE IF EXISTS ${TABLE_NAME};"
echo "Table '${TABLE_NAME}' has been deleted."

echo "Script execution complete."
