#-*- coding: utf-8 -*-
import time
from flask import Blueprint,render_template,g,request,make_response,flash
from Modules import loging,check,produce,db_idc,tools
import string
import redis
import datetime
from pyecharts import Gauge,Line,Bar
from flask import Flask
from collections import defaultdict
from flask_sqlalchemy import SQLAlchemy
app = Flask(__name__)
app.config.from_pyfile('conf/redis.conf')
app.config.from_pyfile('conf/sql.conf')
DB = SQLAlchemy(app)
logging = loging.Error()
redis_host = app.config.get('REDIS_HOST')
redis_port = app.config.get('REDIS_PORT')
redis_password = app.config.get('REDIS_PASSWORD')
RC = redis.StrictRedis(host=redis_host, port=redis_port,decode_responses=True)
redis_data = app.config.get('REDIS_DATA')
RC_CLUSTER = redis.StrictRedis(host=redis_data, port=redis_port,decode_responses=True)
page_index=Blueprint('index',__name__)
@page_index.route('/index')
def index():
    try:
        whitelist = []
        Key = "op_alarm_load_whitelist"
        if RC_CLUSTER.exists(Key):
            whitelist = RC_CLUSTER.smembers(Key)
        td = time.strftime("%Y-%m-%d", time.localtime())
        td_1 = datetime.datetime.now() - datetime.timedelta(days=1)
        td_1 = td_1.strftime("%Y-%m-%d")
        td_7 = datetime.datetime.now() - datetime.timedelta(days=7)
        td_7 = td_7.strftime("%Y-%m-%d")
        TM = time.strftime('%M', time.localtime())
        BUSIS = []
        #业务信息展示
        try:
            Key = 'op_k8s_ingress_log'
            k8s_domains_key = 'op_k8s_domains_%s' % td
            total_key = 'op_totals_alarms_tmp'
            if RC.exists(k8s_domains_key):
                try:
                    line = Line("容器平台业务RPS统计", width='105%', height=250, title_pos='center', title_text_size=12)
                    for domain in RC.smembers(k8s_domains_key):
                        if RC.exists('%s_%s_%s' % (Key, domain,td)):
                            vals = RC.hgetall('%s_%s_%s' % (Key, domain,td))
                            vals = sorted(vals.items(), key=lambda item:item[0])
                            attrs = [val[0] for val in vals[-10:]]
                            vals = [int(int(val[1])/60) for val in vals[-10:]]
                            line.add(domain, attrs, vals, is_label_show=True, is_toolbox_show=False,legend_pos='65%',
                                     xaxis_interval=0, is_fill=True, area_opacity=0.3, is_smooth=True)
                except Exception as e:
                    logging.error(e)
            else:
                for i in range(7):
                    data_now = datetime.datetime.now() - datetime.timedelta(days=i)
                    dd = data_now.strftime('%Y-%m-%d')
                    alarm_count_key = '%s_%s' % ('op_business_alarm_count', dd)
                    if RC_CLUSTER.exists(alarm_count_key):
                        vals = RC_CLUSTER.hgetall(alarm_count_key)
                        vals = sorted(vals.items(), key=lambda item: int(item[1]))
                        for val in vals:
                            RC_CLUSTER.hincrby(total_key, dd, val[1])
                line = Line("业务监控报警近期统计", width='105%', height=250, title_pos='center', title_text_size=12)
                if RC_CLUSTER.exists(total_key):
                    vals = RC_CLUSTER.hgetall(total_key)
                    vals = sorted(vals.items(), key=lambda item: item[0],reverse=True)
                    RC_CLUSTER.delete(total_key)
                    attrs = [val[0] for val in vals]
                    vals = [int(val[1]) for val in vals]
                    line.add("", attrs, vals, is_label_show=True, is_toolbox_show=False,is_legend_show  = False,
                             xaxis_interval=0,is_fill=True,area_opacity=0.3,is_smooth=True)
            bar = Bar("线上业务实时PV统计", width='105%', height=250, title_pos='center', title_text_size=12)
            busi_vals = RC_CLUSTER.hgetall('op_business_pv_%s' %td)
            if busi_vals:
                busi_vals = sorted(busi_vals.items(), key=lambda item: int(float(item[1])), reverse=True)
                bar_vals = [val[0] for val in busi_vals[:8]]
                bar_counts = [float('%.4f' %(float(val[1])/100000000)) for val in busi_vals[:8]]
                bar.add("", bar_vals, bar_counts, is_label_show=True, is_toolbox_show=False, legend_orient='vertical',
                        legend_pos='right', xaxis_interval=0,yaxis_formatter='亿')
            BUSIS.extend((bar,line))
        except Exception as e:
            logging.error(e)
        #网站并发访问展示
        try:
            NEW_DATA = [eval(v) for v in RC.lrange('internet_access_%s' %td, 0, -1)]
            attr = [DATA[0] for DATA in NEW_DATA]
            vals =[int(int(DATA[1])/60) for DATA in NEW_DATA]
            line = Line('墨迹线上业务RPS统计',title_pos='center',title_text_size=12,width='109%',height='250px')
            line.add("今天", attr, vals,is_toolbox_show=False,is_smooth=True,mark_point=["max", "min"],
                     mark_point_symbolsize=80,is_datazoom_show=True,datazoom_range=[v for v in range(100,10)],
                     datazoom_type= 'both',legend_pos='70%')
            if RC.exists('internet_access_%s' % td_1):
                OLD_DATA = [eval(v) for v in RC.lrange('internet_access_%s' % td_1, 0, -1)]
                OLD_DATA = [val for val in OLD_DATA if val[0] in attr]
                old_attr = [DATA[0] for DATA in OLD_DATA]
                old_vals = [int(int(DATA[1]) / 60) for DATA in OLD_DATA]
                if attr and vals:
                    line.add("昨天", old_attr,old_vals, is_toolbox_show=False, is_smooth=True, mark_point=["max", "min"],
                             mark_point_symbolsize=80,is_datazoom_show=True,datazoom_range=[v for v in range(100,10)],
                             datazoom_type= 'both',legend_pos='70%')
            if RC.exists('internet_access_%s' % td_7):
                OLD_DATA = [eval(v) for v in RC.lrange('internet_access_%s' % td_7, 0, -1)]
                OLD_DATA = [val for val in OLD_DATA if val[0] in attr]
                old_attr = [DATA[0] for DATA in OLD_DATA]
                old_vals = [int(int(DATA[1]) / 60) for DATA in OLD_DATA]
                if attr and vals:
                    line.add("上周", old_attr,old_vals, is_toolbox_show=False, is_smooth=True, mark_point=["max", "min"],
                             mark_point_symbolsize=80, is_datazoom_show=True, datazoom_range=[v for v in range(100, 10)],
                             datazoom_type='both', legend_pos='70%')
        except Exception as e:
            logging.error(e)
        #监控数据展示
        try:
            tm = datetime.datetime.now() - datetime.timedelta(minutes=1)
            tm = tm.strftime('%H:%M')
            z_triggers = RC.hgetall('zabbix_triggers_%s' %tm)
            if z_triggers:
                z_triggers = [[t,z_triggers[t]]for t in z_triggers]
        except Exception as e:
            logging.error(e)
        #服务器预警信息
        try:
            z_infos = defaultdict()
            dict_load = None
            dict_openfile = None
            if RC_CLUSTER.exists('op_zabbix_server_load_top'):
                dict_load = eval(RC_CLUSTER.get('op_zabbix_server_load_top'))
            if RC_CLUSTER.exists('op_zabbix_server_openfile_top'):
                dict_openfile = eval(RC_CLUSTER.get('op_zabbix_server_openfile_top'))
            if dict_load:
                z_infos['cpu_load']=dict_load
            if dict_openfile:
                z_infos['openfile'] = dict_openfile
        except Exception as e:
            logging.error(e)
        # 获取问题服务器列表
        fault_servers = defaultdict()
        try:
            for key in ('ssh_login_fault_%s'%td, 'ssh_port_fault_%s'%td):
                if RC.exists(key):
                    fault_vals = RC.hgetall(key)
                    if fault_vals:
                        fault_servers[key] = zip([fault_vals[val] for val in fault_vals],[val.split(':')[0] for val in fault_vals],[val.split(':')[1] for val in fault_vals])
        except Exception as e:
            logging.error(e)
        app_resp = make_response(render_template('index.html',line=line,tm=TM,z_triggers=z_triggers,z_infos=z_infos,fault_servers=fault_servers,BUSIS=BUSIS,whitelist=whitelist))
        app_resp.set_cookie('secret_key',tools.Produce(length=8,chars=string.digits),path='/')
        return app_resp
    except Exception as e:
        logging.error(e)
        flash('获取数据错误!',"error")
        return render_template('Message.html')

@page_index.route('/alarm_show')
def alarm_show():
    try:
        whitelist = []
        Key = "op_alarm_load_whitelist"
        if RC_CLUSTER.exists(Key):
            whitelist = RC_CLUSTER.smembers(Key)
        td = time.strftime("%Y-%m-%d", time.localtime())
        BUSIS = []
        try:
            tm = datetime.datetime.now() - datetime.timedelta(minutes=1)
            tm = tm.strftime('%H:%M')
            z_triggers = RC.hgetall('zabbix_triggers_%s' %tm)
            if z_triggers:
                z_triggers = [[t,z_triggers[t]]for t in z_triggers]
        except Exception as e:
            logging.error(e)
        #服务器预警信息
        try:
            z_infos = defaultdict()
            dict_load = None
            dict_openfile = None
            if RC_CLUSTER.exists('op_zabbix_server_load_top'):
                dict_load = eval(RC_CLUSTER.get('op_zabbix_server_load_top'))
            if RC_CLUSTER.exists('op_zabbix_server_openfile_top'):
                dict_openfile = eval(RC_CLUSTER.get('op_zabbix_server_openfile_top'))
            if dict_load:
                z_infos['cpu_load']=dict_load
            if dict_openfile:
                z_infos['openfile'] = dict_openfile
        except Exception as e:
            logging.error(e)
        # 获取问题服务器列表
        fault_servers = defaultdict()
        try:
            for key in ('ssh_login_fault_%s'%td, 'ssh_port_fault_%s'%td):
                if RC.exists(key):
                    fault_vals = RC.hgetall(key)
                    if fault_vals:
                        fault_servers[key] = zip([fault_vals[val] for val in fault_vals],[val.split(':')[0] for val in fault_vals],[val.split(':')[1] for val in fault_vals])
        except Exception as e:
            logging.error(e)
        return render_template('alarm_show.html',z_triggers=z_triggers,z_infos=z_infos,fault_servers=fault_servers,BUSIS=BUSIS,whitelist=whitelist)
    except Exception as e:
        logging.error(e)
        flash('获取数据错误!',"error")
        return render_template('Message.html')
@page_index.before_request
@check.login_required(grade=10)
def check_login(exception = None):
    produce.Async_log(g.user, request.url)
@page_index.teardown_request
def db_remove(exception):
    db_idc.DB.session.remove()