#!/bin/bash
# bash launch.sh [1|2]
# $1: 1 for with perf, 2 for without perf
MYSQL_USER=root
MYSQL_BASEDIR=
MYSQL_WORKSPACE=

MYSQL_CMD="$MYSQL_BASEDIR/bin/mysql -u $MYSQL_USER --skip-password --socket=$MYSQL_WORKSPACE/mysql.sock"

MYSQL_DB="test"

# add hints if there is not designated user
if [[ -z $MYSQL_USER ]]; then
    echo "No user specified"
    # abort
    exit 1
fi

# get the bash pid
echo "Script PID: $$"

# Compile the test program to get timestamp in nanoseconds
clang++ -O2 get_timestamp.cpp -o get_timestamp

# make the output directory
if [[ $1 == 1 ]]; then
    LOG_DIR="my-outputs/with_perf"
elif [[ $1 == 2 ]]; then
    LOG_DIR="my-outputs/without_perf"
fi
rm -rf $LOG_DIR
mkdir -p $LOG_DIR

# prepare the logs
MYSQL_OUT_FILE=$LOG_DIR/mysql.out

# prepare the database
echo "Preparing the database..."
DB_EXISTS=$($MYSQL_CMD -e "SHOW DATABASES LIKE '$MYSQL_DB';" | grep "$MYSQL_DB")

if [[ -z "$DB_EXISTS" ]]; then
    echo "Database $MYSQL_DB does not exist. Creating it..."
    $MYSQL_CMD -e "CREATE DATABASE $MYSQL_DB;" || { echo "Failed to create database $MYSQL_DB"; exit 1; }
else
    echo "Database $MYSQL_DB already exists."
fi

# prepare the scenario
echo "Preparing the scenario..."
TABLE_NAME="t1"
$MYSQL_CMD -e "USE ${MYSQL_DB}; DROP TABLE IF EXISTS ${TABLE_NAME};"
echo "Creating table '${TABLE_NAME}'..."
$MYSQL_CMD -e "USE ${MYSQL_DB}; CREATE TABLE ${TABLE_NAME} (i INT(11) NOT NULL AUTO_INCREMENT PRIMARY KEY, c CHAR(32) NOT NULL DEFAULT 'dummy_text') ENGINE=InnoDB;"
echo "Inserting data..."
for i in $(seq 1 100); do
    $MYSQL_CMD -e "
    USE ${MYSQL_DB};
    INSERT INTO ${TABLE_NAME} (i, c) VALUES ($i, 'dummy_text');"
done

# launch background sysbench
SYSBENCH_LUA=/usr/share/sysbench/oltp_update_index.lua
SYSBENCH_CMD="sysbench $SYSBENCH_LUA --threads=10 --report-interval=1 --time=80 --max-requests=0 --rand-type=uniform --mysql-user=$MYSQL_USER --mysql-password= --mysql-db=$MYSQL_DB --mysql-socket=$MYSQL_WORKSPACE/mysql.sock"
rm -f $LOG_DIR/sysbench.out
$SYSBENCH_CMD cleanup
$SYSBENCH_CMD prepare
$SYSBENCH_CMD run >>$LOG_DIR/sysbench.out 2>&1 &
sysbench_pid=$!
trap "kill $sysbench_pid; exit" SIGINT
echo "Started sysbench"
echo "Current Timestamp:"
./get_timestamp
sleep 4

# prefetch mysqld pid
mysqld_pid=$(ps -ef | grep mysqld | sed -n 2p | awk '{print $2}')
echo "MySQL PID: $mysqld_pid"


function run_with_perf {
    echo "Running the case with perf"
    echo "monitoring begins" >> $LOG_DIR/sysbench.out
    sleep 6
    echo "monitoring ends" >> $LOG_DIR/sysbench.out

    perf record -e cpu-clock:u --call-graph dwarf -s -F 100 --pid=$mysqld_pid &
    perf_pid=$!
    trap "kill $perf_pid; exit" SIGINT
	echo "Trans started. Current Timestamp:"
	./get_timestamp

    (
        # transaction 1
        $MYSQL_CMD -e "
        USE ${MYSQL_DB};
        START TRANSACTION;
        SELECT * FROM ${TABLE_NAME} LIMIT 10;
        DO SLEEP(60);
        COMMIT;"
    ) &
    trans_1_pid=$!
    echo "transaction 1 PID: $trans_1_pid"

    (
        # transaction 2
        echo "Start alter transaction"
        sleep 1  
        $MYSQL_CMD -e "
        USE ${MYSQL_DB};
        START TRANSACTION;
        ALTER TABLE ${TABLE_NAME} ADD KEY k2(c);"
    ) &
    trans_2_pid=$!
    echo "transaction 2 PID: $trans_2_pid"

    echo "perf attached" >> $LOG_DIR/sysbench.out
	wait $trans_2_pid
	echo "transaction 2 ends"
    wait $trans_1_pid
    echo "transaction 1 ends"
    kill $perf_pid
    echo "perf detached" >> $LOG_DIR/sysbench.out

    echo "waiting sysbench to finish, pid: $sysbench_pid"
    wait $sysbench_pid
}

function run_without_perf {
    echo "Running the case without perf"
    echo "monitoring begins" >> $LOG_DIR/sysbench.out
    sleep 6
    echo "monitoring ends" >> $LOG_DIR/sysbench.out
	echo "Trans started. Current Timestamp:"
	./get_timestamp

    (
        # transaction 1
        $MYSQL_CMD -e "
        USE ${MYSQL_DB};
        START TRANSACTION;
        SELECT * FROM ${TABLE_NAME} LIMIT 10;
        DO SLEEP(60);
        COMMIT;"
    ) &
    trans_1_pid=$!
    echo "transaction 1 PID: $trans_1_pid"

    (
        # transaction 2
        echo "Start alter transaction"
        sleep 1  
        $MYSQL_CMD -e "
        USE ${MYSQL_DB};
        START TRANSACTION;
        ALTER TABLE ${TABLE_NAME} ADD KEY k2(c);"
    ) &
    trans_2_pid=$!
    echo "transaction 2 PID: $trans_2_pid"

    echo "perf attached (mock)" >> $LOG_DIR/sysbench.out
	wait $trans_2_pid
	echo "transaction 2 ends. Current Timestamp:"
	./get_timestamp
    wait $trans_1_pid
	echo "transaction 1 ends. Current Timestamp:"
	./get_timestamp
    echo "perf detached (mock)" >> $LOG_DIR/sysbench.out

    echo "waiting sysbench to finish, pid: $sysbench_pid"
    wait $sysbench_pid
	echo "Test completed. Current Timestamp:"
	./get_timestamp
}

if [[ $1 == 1 ]]; then
    run_with_perf
elif [[ $1 == 2 ]]; then
    run_without_perf
fi

echo "Done"
echo "Done" >> $LOG_DIR/sysbench.out
