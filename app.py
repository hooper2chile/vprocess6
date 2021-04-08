#!/usr/bin/env python
# -*- coding: utf-8 -*-
#vprocess6 - CECS: Felipe Hooper 18 de Febrero
from flask import Flask, render_template, session, request, Response, send_from_directory, make_response
from flask_socketio import SocketIO, emit, disconnect

import os, sys, time, datetime,logging, communication, reviewDB, tocsv, zmq
DIR="/home/pi/vprocess6"

logging.basicConfig(filename= DIR + '/log/app.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')



#CREDENCIALES PARA PAGINAS WEB
USER   = "Biocl_CECS"
PASSWD = "cecs"

SPEED_MAX = 150 #150 [rpm]
TEMP_MAX  = 50 #130 [C]
TIME_MAX  = 99  #99 [min]

u_set_temp = [SPEED_MAX,0]
u_set_ph   = [SPEED_MAX,SPEED_MAX]

ph_set = [0,0,0,0]
od_set = [0,0,0,0]
temp_set = [0,0,0,0]

calibrar_ph   = ""
calibrar_temp = ""

rm3     =  0
rm5     =  0
rm_sets = [0,0,0,0,0,0]  #se agrega rm_sets[5] para enviar este al uc
rm_save = [0,0,0,0,0,0]  #mientras que rm_sets[4] se usara solo en app.py para los calculos de tiempo

task = ["grabar", False]
flag_database = False
#            0   1   2    3   4    5 6 7 8 9 10 11 12 13
#set_data = [10, 0, 7.0, 10, 25.0, 1,1,1,1,1,0, 0, 0, 0]  # increiblemente uno de estos hacia partir en activado el sistema de motores...
set_data = [10,  60, 7.0, 10, 25,   1,1,1,1,1,0, 0, 0, 0]
#set_data[1] =: setpoint mix
#set_data[8] =: rst2 (reset de bomba2)
#set_data[9] =: rst3 (reset de bomba temperatura)
#set_data[5] =: rst1 (reset de bomba1)
#rm_sets[4]  =: (reset global de bomba remontaje)
#rm_sets[5]  =: (reset local de bomba remontaje)


ficha_producto = [0.0,0.0,0.0,0.0,0.0,"vacio_cecs-k","vacio_cecs-g",0,0.0,0,0,0,0] #ficha_producto[9]=set_data[4]:temparatura setpoint
ficha_producto_save = ficha_producto                                  #ficha_producto[10] = set_data[0]: bomba1
                                                                      #ficha_producto[11] = set_data[3]: bomba2
                                                                      #ficha_producto[12] = rm_sets[4]*rm_sets[5] : para saber cuando
                                                                      #enciende y cuando apaga el remontaje y se multiplica por el flujo en base de datos.

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

#app = Flask(__name__)
app = Flask(__name__, static_url_path="")
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread1 = None
error = None

#CONFIGURACION DE PAGINAS WEB
@app.route('/'     , methods=['POST', 'GET'])
@app.route('/login', methods=['POST', 'GET'])
def login():
    global error

    if request.method == 'POST':
        if request.form['username'] != USER or request.form['password'] != PASSWD:
            error = "Credencial Invalida"
            return render_template("login.html", error=error)
        else:
            error='validado'
            return render_template("index.html", error=error)

    error="No Validado en login"
    return render_template("login.html", error=error)




@app.route('/calibrar', methods=['POST', 'GET'])
def calibrar():
    global error

    if request.method == 'POST':
        if request.form['username'] != USER or request.form['password'] != PASSWD:
            error = "Credencial Invalida"
            return render_template("login.html", error=error)
        else:
            error='validado'
            return render_template("calibrar.html", error=error)

    error = 'No Validado en Calibracion'
    return render_template("login.html", error=error)




@app.route('/graphics')
def graphics():
    return render_template('graphics.html', title_html="Variables de Proceso")


@app.route('/dbase', methods=['GET', 'POST'])
def viewDB():
    return render_template('dbase.html', title_html="Data Logger")




#CONFIGURACION DE FUNCIONES SocketIO
#Connect to the Socket.IO server. (Este socket es OBLIGACION)
@socketio.on('connect', namespace='/biocl')
def function_thread():
    #print "\n Cliente Conectado al Thread del Bioreactor\n"
    #logging.info("\n Cliente Conectado al Thread del Bioreactor\n")

#Se emite durante la primera conexión de un cliente el estado actual de los setpoints
    emit('Setpoints',           {'set': set_data})
    emit('ph_calibrar',         {'set': ph_set})
    emit('od_calibrar',         {'set': od_set})
    emit('temp_calibrar',       {'set': temp_set})
    emit('u_calibrar',          {'set': u_set_ph})
    emit('u_calibrar_temp',     {'set': u_set_temp})
    emit('power',               {'set': task})
    emit('remontaje_setpoints', {'set': rm_sets, 'save': rm_save })
    emit('producto'           , {'set': ficha_producto, 'save': ficha_producto_save})


    global thread1
    if thread1 is None:
        thread1 = socketio.start_background_task(target=background_thread1)




@socketio.on('power', namespace='/biocl')
def setpoints(dato):
    global task, flag_database
    #se reciben los nuevos setpoints
    task = [ dato['action'], dato['checked'] ]

    #guardo task en un archivo para depurar
    try:
        f = open(DIR + "/task.txt","a+")
        f.write(str(task) + '\n')
        f.close()

    except:
        pass
        #logging.info("no se pudo guardar en realizar en task.txt")


    #Con cada cambio en los setpoints, se vuelven a emitir a todos los clientes.
    socketio.emit('power', {'set': task}, namespace='/biocl', broadcast=True)

    if task[1] is True:
        if task[0] == "grabar":
            flag_database = "True"
            try:
                f = open(DIR + "/flag_database.txt","w")
                f.write(flag_database)
                f.close()

            except:
                pass
                #logging.info("no se pudo guardar el flag_database para iniciar grabacion\n")

        elif task[0] == "no_grabar":
            flag_database = "False"
            try:
                #os.system("rm -rf" + DIR + "/name_db.txt")
                f = open(DIR + "/flag_database.txt","w")
                f.write(flag_database)
                f.close()

            except:
                pass
                #logging.info("no se pudo guardar el flag_database para detener grabacion\n")

        elif task[0] == "reiniciar":
            os.system(DIR + "bash killall")
            os.system("rm -rf " + DIR + "/database/*.db-journal")
            os.system("rm -rf " + DIR + "/*.txt")

            os.system("sudo reboot")

        elif task[0] == "apagar":
            os.system("bash" + DIR + "/killall")
            os.system("sudo shutdown -h now")

        elif task[0] == "limpiar":
            try:
                os.system("rm -rf " + DIR + "/csv/*.csv")
                os.system("rm -rf " + DIR + "/log/*.log")
                os.system("rm -rf " + DIR + "/log/my.log.*")
                os.system("rm -rf " + DIR + "/database/*.db")
                os.system("rm -rf " + DIR + "/database/*.db-journal")

                f = open(DIR + "/limpiar.txt","w")
                f.write("entro en el elif == limpiar\n")
                f.close()

            except:
                f = open(DIR + "/limpiar.txt","w")
                f.write("entro en la except de limpiar\n")
                f.close()
                pass
                #logging.info("no se pudo completar limpiar\n")

        else:
            f = open(DIR + "/limpiar.txt","w")
            f.write("se metio en el else de task[0]\n")
            f.close()




N = None
APIRest = None
@socketio.on('my_json', namespace='/biocl')
def my_json(dato):

    dt  = int(dato['dt'])
    var = dato['var']

    try:
        f = open(DIR + "/window.txt","a+")
        f.write(dato['var'] + ' ' + dato['dt'] +'\n')
        f.close()

    except:
        #print "no se logro escribir la ventana solicitada en el archivo window.txt"
        pass
        #logging.info("no se logro escribir la ventana solicitada en el archivo window.txt")

    #Se buscan los datos de la consulta en database
    try:
        f = open(DIR + "/name_db.txt",'r')
        filedb = f.readlines()[-1][:-1]
        f.close()

    except:
        #print "no se logro leer nombre de ultimo archivo en name_db.txt"
        pass
        #logging.info("no se logro leer nombre de ultimo archivo en name_db.txt")

    global APIRest
    APIRest = reviewDB.window_db(filedb, var, dt)
    socketio.emit('my_json', {'data': APIRest, 'No': len(APIRest), 'var': var}, namespace='/biocl')
    #put files in csv with dt time for samples
    tocsv.csv_file(filedb, dt)


@socketio.on('Setpoints', namespace='/biocl')
def setpoints(dato):
    global set_data, save_set_data
    #se reciben los nuevos setpoints
    set_data = [ dato['alimentar'], dato['mezclar'], dato['ph'], dato['descarga'], dato['temperatura'], dato['alimentar_rst'], dato['mezclar_rst'], dato['ph_rst'], dato['descarga_rst'], dato['temperatura_rst'], dato['alimentar_dir'], dato['ph_dir'], dato['temperatura_dir'], dato['descarga_dir']  ]

    try:
        set_data[0] = int(set_data[0])   #alimentar (bomba1)
        set_data[1] = int(set_data[1])   #mezclar
        set_data[2] = float(set_data[2]) #ph
        set_data[3] = int(set_data[3])   #descarga  (bomba2)
        set_data[4] = int(set_data[4])   #temperatura

        #rst setting
        set_data[5] = int(set_data[5])  #alimentar_rst
        set_data[6] = int(set_data[6])  #mezclar_rst
        set_data[7] = int(set_data[7])  #ph_rst
        set_data[8] = int(set_data[8])  #descarga_rst
        set_data[9] = int(set_data[9])  #temperatura_rst

        #dir setting
        set_data[10]= int(set_data[10]) #alimentar_dir
        set_data[11]= int(set_data[11]) #ph_dir
        set_data[12]= int(set_data[12]) #temperatura_dir
        set_data[13]= int(set_data[13]) #descarga_dir

        save_set_data = set_data

    except ValueError:
        set_data = save_set_data #esto permite reenviar el ultimo si hay una exception
        #logging.info("exception de set_data")

    #Con cada cambio en los setpoints, se vuelven a emitir a todos los clientes.
    socketio.emit('Setpoints', {'set': set_data}, namespace='/biocl', broadcast=True)

    #guardo set_data en un archivo para depurar
    try:
        f = open(DIR + "/setpoints.txt","a+")
        f.write( str(set_data) + "  " + time.strftime("Hora__%H_%M_%S__Fecha__%d-%m-%y") + '\n')              #agregar fecha y hora a este string
        f.close()

    except:
        pass
        #logging.info("no se pudo guardar en set_data en setpoints.txt")



@socketio.on('producto', namespace='/biocl')
def ficha(dato):
    global ficha_producto

    try:
        ficha_producto[0] = float(dato['cultivo'])
        ficha_producto[1] = float(dato['tasa'])
        ficha_producto[2] = float(dato['biomasa'])
        ficha_producto[3] = float(dato['sustrato'])

        #ficha_producto_save = ficha_producto  #esta sobre escribiendo

    except:
        ficha_producto = ficha_producto_save
        #logging.info("no se pudo evaluar la ficha de producto")

    socketio.emit('producto', {'set':ficha_producto, 'save': ficha_producto_save}, namespace='/biocl', broadcast=True)
    #communication.zmq_client_data_speak_website(ficha_producto)



#CALIBRACION OXIGENO DISUELTO
@socketio.on('od_calibrar', namespace='/biocl')
def calibrar_od(dato):
    global od_set
    #se reciben los parametros para calibración
    setting = [ dato['od'], dato['iod'], dato['medx'] ]

    #ORDEN DE: od_set:
    #ph_set = [od1_set, iod1_set, od2_set, iod2_set]
    try:
        if setting[2] == 'med1':
            od_set[0] = float(dato['od'])
            od_set[1] = float(dato['iod'])

        elif setting[2] == 'med2':
            od_set[2] = float(dato['od'])
            od_set[3] = float(dato['iod'])

    except:
        od_set = [0,0,0,0]


    if (od_set[3] - od_set[1])!=0 and od_set[1]!=0:
        m_od = float(format(( od_set[2] - od_set[0] )/( od_set[3] - od_set[1] ), '.2f'))
        n_od = float(format(  od_set[0] - od_set[1]*(m_od), '.2f'))

    else:
        m_od = 0
        n_od = 0

    if od_set[1]!=0 and od_set[3]!=0 and m_od!=0 and n_od!=0:
        try:
            coef_od_set = [m_od, n_od]
            f = open(DIR + "/coef_od_set.txt","w")
            f.write(str(coef_od_set) + time.strftime("__Hora__%H_%M_%S__Fecha__%d-%m-%y") + '\n')
            f.close()

            #acá va el codigo que formatea el comando de calibración.
            calibrar_od = communication.calibrate(1,coef_od_set)
            #Publisher set_data commands al ZMQ suscriptor de myserial.py
            port = "5556"
            context = zmq.Context()
            socket = context.socket(zmq.PUB)
            socket.bind("tcp://*:%s" % port)
            #Publisher set_data commands
            socket.send_string("%s %s" % (topic, calibrar_od))


        except:
            pass
            #logging.info("no se pudo guardar en coef_ph_set en coef_od_set.txt")


    #Con cada cambio en los parametros, se vuelven a emitir a todos los clientes.
    socketio.emit('od_calibrar', {'set': od_set}, namespace='/biocl', broadcast=True)

    #guardo set_data en un archivo para depurar
    try:
        od_set_txt = str(od_set)
        f = open(DIR + "/od_set.txt","w")
        f.write(od_set_txt + '\n')
        f.close()

    except:
        pass
        #logging.info("no se pudo guardar parameters en od_set.txt")



#Sockets de calibración de instrumentación
#CALIBRACION DE PH
@socketio.on('ph_calibrar', namespace='/biocl')
def calibrar_ph(dato):
    global ph_set, calibrar_ph
    #se reciben los parametros para calibración
    setting = [ dato['ph'], dato['iph'], dato['medx'] ]

    #ORDEN DE: ph_set:
    #ph_set = [ph1_set, iph1_set, ph2_set, iph2_set]
    try:
        if setting[2] == 'med1':
            ph_set[0] = float(dato['ph'])   #y1
            ph_set[1] = float(dato['iph'])  #x1

        elif setting[2] == 'med2':
            ph_set[2] = float(dato['ph'])   #y2
            ph_set[3] = float(dato['iph'])  #x2

    except:
        ph_set = [0,0,0,0]

    if (ph_set[3] - ph_set[1])!=0 and ph_set[0]!=0 and ph_set[1]!=0:
        m_ph = float(format(( ph_set[2] - ph_set[0] )/( ph_set[3] - ph_set[1] ), '.2f'))
        n_ph = float(format(  ph_set[0] - ph_set[1]*(m_ph), '.2f'))

    else:
        m_ph = 0
        n_ph = 0

    if ph_set[0]!=0 and ph_set[1]!=0 and ph_set[2]!=0 and ph_set[3]!=0 and m_ph!=0 and n_ph!=0:
        try:
            coef_ph_set = [m_ph, n_ph]
            f = open(DIR + "/ph_settings.txt","w")
            f.write(str(ph_set) + "__" + str(coef_ph_set) + "__" + calibrar_ph + " " + time.strftime("__Hora__%H_%M_%S__Fecha__%d-%m-%y") +'\n')
            f.close()

            #acá va el codigo que formatea el comando de calibración.
            calibrar_ph = communication.calibrate(0,coef_ph_set)
            #Publisher set_data commands al ZMQ suscriptor de myserial.py
            port = "5556"
            context = zmq.Context()
            socket = context.socket(zmq.PUB)
            socket.bind("tcp://*:%s" % port)
            #Publisher set_data commands
            socket.send_string("%s %s" % (topic, calibrar_ph))


        except:
            pass
            #logging.info("no se pudo guardar en coef_ph_set.txt. Tampoco actualizar los coef_ph_set al uc.")

    #Con cada cambio en los parametros, se vuelven a emitir a todos los clientes.
    socketio.emit('ph_calibrar', {'set': ph_set}, namespace='/biocl', broadcast=True)

    #guardo ph_set en un archivo para depurar
    try:
        ph_set_txt = str(ph_set)
        f = open(DIR + "/ph_set.txt","w")
        f.write(ph_set_txt + '\n')
        f.close()

    except:
        pass
        #logging.info("no se pudo guardar parameters en od_set.txt")


########################## se debe actualizar para los sensores atlas scientific #########################
#CALIBRACIÓN TEMPERATURA
@socketio.on('temp_calibrar', namespace='/biocl')
def calibrar_temp(dato):
    global temp_set, calibrar_temp
    #se reciben los parametros para calibración
    setting = [ dato['temp'], dato['itemp'], dato['medx'] ]

    try:
        temp_set = str(dato['temp'])
        calibrar_temp = 't' + temp_set

        f = open(DIR + "/coef_temp_set.txt","w")
        f.write( temp_set + "  " + calibrar_temp + "  " + time.strftime("__Hora__%H_%M_%S__Fecha__%d-%m-%y") + '\n')
        f.close()

    except:
        logging.info("no se pudo guardar en coef_ph_set en coef_od_set.txt")


    #Con cada cambio en los parametros, se vuelven a emitir a todos los clientes.
    socketio.emit('temp_calibrar', {'set': temp_set}, namespace='/biocl', broadcast=True)




#CALIBRACION ACTUADOR PH
@socketio.on('u_calibrar', namespace='/biocl')
def calibrar_u_ph(dato):
    global u_set_ph
    #se reciben los parametros para calibración
    #setting = [ dato['u_acido_max'], dato['u_base_max'] ]
    try:
        u_set_ph[0] = int(dato['u_acido_max'])
        u_set_ph[1] = int(dato['u_base_max'])

    except:
        u_set_ph = [SPEED_MAX,SPEED_MAX]


    try:
        f = open(DIR + "/umbral_set_ph.txt","w")
        f.write(str(u_set_ph) + '\n')
        f.close()
        communication.actuador(1,u_set_ph)  #FALTA IMPLEMENTARIO EN communication.py

    except:
        pass
        #logging.info("no se pudo guardar umbrales u_set_ph en umbral_set_ph.txt")


    #Con cada cambio en los parametros, se vuelven a emitir a todos los clientes.
    socketio.emit('u_calibrar', {'set': u_set_ph}, namespace='/biocl', broadcast=True)



#CALIBRACION ACTUADOR TEMP
@socketio.on('u_calibrar_temp', namespace='/biocl')
def calibrar_u_temp(dato):
    global u_set_temp
    #se reciben los parametros para calibración

    try:
        u_set_temp[0] = int(dato['u_temp'])
        u_set_temp[1] = 0

    except:
        u_set_temp = [SPEED_MAX,SPEED_MAX]


    try:
        f = open(DIR + "/umbral_set_temp.txt","w")
        f.write(str(u_set_temp) + time.strftime("__Hora__%H_%M_%S__Fecha__%d-%m-%y") + '\n')
        f.close()
        communication.actuador(2,u_set_temp)  #FALTA IMPLEMENTARIO EN communication.py

    except:
        pass
        #logging.info("no se pudo guardar u_set_temp en umbral_set_temp.txt")


    #Con cada cambio en los parametros, se vuelven a emitir a todos los clientes.
    socketio.emit('u_calibrar_temp', {'set': u_set_temp}, namespace='/biocl', broadcast=True)





#CONFIGURACION DE THREADS
def background_thread1():
    measures = [0,0,0,0,0,0,0]
    measures_save = measures
    global save_set_data, set_data
    save_set_data = [20,0,0,20,0,1,1,1,1,1,0,0,0]

    topic   = 'w'
    #####Publisher part: publicador zmq para el suscriptor de ficha_producto en la base de datos.
    port_pub = "5554"
    context_pub = zmq.Context()
    socket_pub = context_pub.socket(zmq.PUB)
    socket_pub.bind("tcp://*:%s" % port_pub)
    #####Publisher part: publica las lecturas obtenidas al zmq suscriptor de la base de datos.

    #Publisher set_data commands al ZMQ suscriptor de myserial.py
    port = "5556"
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind("tcp://*:%s" % port)
    #Publisher set_data commands

    #####Listen measures (suscriptor de las mediciones)
    port_sub = "5557"
    context_sub = zmq.Context()
    socket_sub = context_sub.socket(zmq.SUB)
    socket_sub.connect ("tcp://localhost:%s" % port_sub)
    topicfilter = "w"
    socket_sub.setsockopt(zmq.SUBSCRIBE, topicfilter)
    #####Listen measures

    while True:
        global save_set_data, set_data, rm_sets, rm_save, ficha_producto, rm3, rm5, calibrar_ph, calibrar_temp

        #desde aca se envian (publicadores) set_points para myserial.py y dato de ficha producto a database.py
        try:
            #las actualizaciones de abajo deben ir aqui para que aplique la sentencia "!=" en el envio de datos para ficha_producto hacia la Base de Datos
            ficha_producto[9]  = set_data[4]*(1 - set_data[9])  #setpoint de temperatura
            ficha_producto[10] = set_data[0]*(1 - set_data[5])  #bomba1
            ficha_producto[11] = set_data[3]*(1 - set_data[8])  #bomba2
            ficha_producto[4]  = set_data[1]*(1 - set_data[6])  #mezclador
            ficha_producto[8]  = set_data[2]*(1 - set_data[7])  #setpoint pH
            #ficha_producto_save = ficha_producto #se respalda todo lo de ficha_producto
            #preparo la ficha_producto y la envio por ZMQ publicador del canal 5557 a la base de datos
            myList = ','.join(map(str, ficha_producto))
            socket_pub.send_string("%s %s" % (topic, myList))



            #preparo el setpoint y lo mando por el ZMQ publicador del canal 5556 a myserial.py
            send_setpoint = communication.cook_setpoint(set_data,rm_sets)
            socket.send_string("%s %s" % (topic, send_setpoint))

            '''
            #Caso calibrar pH Sensor Hamilton 4-20 mA
            if len(calibrar_ph) == 15:
                #Se envia tres veces por que no toma a la primera en el UC! (RARO!)
                i = 0
                while i <= 2:
                    socketio.sleep(0.1)
                    socket.send_string("%s %s" % (topic, calibrar_ph))
                    i += 1
                calibrar_ph = ""

            '''
            #Caso calibrar Temperatura Sensor Atlas I2C
            if len(calibrar_temp) >= 2:
                #Se envia tres veces por que no toma a la primera en el UC! (RARO!)
                j = 0
                while j <= 2:
                    socketio.sleep(0.1)
                    socket.send_string("%s %s" % (topic, calibrar_temp))
                    j += 1
                calibrar_temp = ""



        except:
            pass
            #logging.info("\n ············· no se pudo enviar datos a los destinatarios ·············\n")


        #ejecuto suscripcion al ZMQ de myserial.py, esto es las mediciones de variables fisicas (esta linea es un suscriptor al puerto 5557)
        try:
            temp_ = socket_sub.recv().split()
            #temp_ = socket_sub.recv(flags=zmq.NOBLOCK).split() #por alguna razon al usar el objeto recv() con el flag NOBLOCK, todo el sistema de ZMQ deja de enviar datos hacia el uc, los motores dejan de funcionar.
            #logging.info("\n Se ejecuto Thread 1 recibiendo %s\n" % measures)

        except zmq.Again:
            pass
            #logging.info("\n NO SE ACTUALIZARON LAS MEDICIONES NI SETPOINTS \n")


        if temp_ != "" and len(temp_) >= 4:
            measures[0] = temp_[1] #Temp
            measures[1] = temp_[3] #pH desde uC y en pestana proceso. FH: 16-02-2021
            measures[2] = temp_[4] #oD en pestana proceso
            measures[3] = temp_[2] #IpH en pestana calibrar
            measures[4] = temp_[5] #Iod en pestana calibrar
            measures[5] = temp_[1] #Itemp en pestana calibrar
            #measures[6] = 22  #Iph
            measures_save = measures

        else:
            measures = measures_save

        #se termina de actualizar y se emiten las mediciones y setpoints para hacia clientes web.-
        socketio.emit('Medidas', {'data': measures, 'set': set_data}, namespace='/biocl')
        socketio.sleep(0.05)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
