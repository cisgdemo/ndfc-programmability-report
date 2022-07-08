##template variables
@(IsInternal=true)
string serial_number;
##
##template content

from collections import OrderedDict

from reportlib.preport import *

from com.cisco.dcbu.vinci.rest.services.jython import InventoryWrapper
from com.cisco.dcbu.vinci.rest.services.jython import WrappersResp
from com.cisco.dcbu.vinci.rest.services.jython import ConfigDeployerWrapper
from utility import *

def generateReport(context):
    report = Report("Switch inventory")
    show_version = 'show version | xml'
    show_inventory = 'show interface transceiver details | xml'
    show_license = 'show license usage | xml'
    
    respObj = WrappersResp.getRespObj()
    
    try:
        platform = exe(InventoryWrapper.getPlatform(serial_number))
        Logger.info("Model name of switch [{}]: {}".format(serial_number, platform))
        if platform.startswith('N'): cli_responses = show_and_store(report, serial_number, show_version, show_inventory, show_license)
        else: 
            summary = report.add_summary()
            summary['Error'] = Formatter.add_marker("Device [{}] of non-Nexus based platforms is not supported!".format(platform), Marker.WARNING)
            Logger.error("Report failed: Device [{}] of non-Nexus based platforms is not supported!".format(platform))
            respObj.setValue(report)
            return respObj
    except Exception as e:
        Logger.error("Report failed: Exception has occured while getting platform and extracting cli_responses for device {}!".format(serial_number) + Util.newLine() + str(e))
        respObj.setFailureRetCode()
        respObj.addErrorReport('switch_inventory',"Exception while processing")
        
    info = {}
    if len(cli_responses) == 1 and 'fail' in cli_responses[0]['status']:
        summary = report.add_summary()
        summary['Error'] = 'Delivery failed due to device connectivity or invalid credential issue.'
        conn_error = report.add_section('Error','error')
        info = { "Error Status": Formatter.add_marker('Switch inventory report could not be generated because of connection issue with switch.', Marker.WARNING),
                'Fix': Formatter.add_marker("Double check credentials to ensure correct authentication. In case of network issues perform the necessary fixes.", Marker.INFO) }
        conn_error.append('Connectivity error', info, "error")
        respObj.setSuccessRetCode()
        respObj.setValue(report)
        return respObj

    eInfo = {}
    for resp in cli_responses:
        command = resp['command'].strip()
        Logger.info(command)
        if show_version in command:
            try: process_show_version(report,resp)
            except:
                eInfo['Error "show version"'] = Formatter.add_marker('There is no parsable output. Please check show command logs for output of "show version" command', Marker.INFO)
        elif show_inventory in command:
            try: process_show_inventory(report,resp)
            except:
                eInfo['Error "show_inventory"'] = Formatter.add_marker('There is no parsable output. Please check show command logs for output of "show inventory" command', Marker.INFO)
        elif show_license in command:
            try: process_show_license_usage(report,resp)
            except:
                eInfo['Error "show license usage"'] = Formatter.add_marker('There is no parsable output. Please check show command logs for output of "show license usage" command', Marker.INFO)

    if eInfo:
        error_info = report.add_section('Errors','error2')
        error_info.append('Processing errors', eInfo, 'error')

    Logger.info("Generating report done!")
    
    respObj.setSuccessRetCode()
    respObj.setValue(report)
    return respObj


def process_show_version(report, show_version):
    Logger.info('Processing show version')
    summary = report.add_summary()
    if "success" in show_version["status"]:
        content = getxmltree(show_version['response'],'__readonly__')
        summary["Device Name"] = getnodevalue(content,'./host_name')
        summary["Chassis ID"] = serial_number
        summary["Model"] = getnodevalue(content,'./chassis_id')
        summary["NXOS version"] = get_OS_version(content)
        uptime = "{} day(s), {} hour(s), {} minute(s), {} second(s)".format(getnodevalue(content,'./kern_uptm_days'),
                                                                            getnodevalue(content,'./kern_uptm_hrs'),
                                                                            getnodevalue(content,'./kern_uptm_mins'),
                                                                            getnodevalue(content,'./kern_uptm_secs'))
        summary["UpTime"] = uptime
    else:
        summary["Error"] = Formatter.add_marker('Command {} is invalid, no output received. Please check command logs for further information.'.format(show_version['command']), Marker.WARNING)

def get_OS_version(xml_tree):
    if has_tag(xml_tree, 'kickstart_ver_str'):
        os_version = getnodevalue(xml_tree,'./kickstart_ver_str')
    elif has_tag(xml_tree, 'kickstart_ver'):
        os_version = getnodevalue(xml_tree,'./kickstart_ver')
    else:
        os_version = 'N/A'
        
    return os_version

def process_show_license_usage(report,show_license_usage):
    content = getxmltree(show_license_usage['response'],'__readonly__')
    Logger.info(str(has_tag(content,'TABLE_show_lic_usage')))
    if has_tag(content,'TABLE_show_lic_usage'):
        process_license_for_all(report,show_license_usage)
    elif has_tag(content,'TABLE_lic_usage'):
        process_license_for_n5k(report,show_license_usage)
    elif has_tag(content,'TABLE_show_smart_lic_usage'):
        process_smart_license(report,show_license_usage)


def process_show_inventory(report, show_inventory):
    Logger.info('Processing show tranceiver example by jaheo')
    module_info = report.add_section("Modules",'Modules')
    if "success" in show_inventory["status"]:
        content = getxmltree(show_inventory['response'],'__readonly__')
        module_rows = getxmlrows(content,'./TABLE_interface/ROW_interface')
        for row in module_rows:
           module_sn = getnodevalue(row,'./interface')
           slot = getnodevalue(row,'./sfp').strip('"')
           data = OrderedDict()
           data['Tranceiver'] = getnodevalue(row,'./interface')
           data['Status'] = getnodevalue(row,'./sfp')
           data['Type'] = getnodevalue(row,'./type')
           data['Part Number'] = getnodevalue(row,'./partnum')
           #data['Type'] = getnodevalue(row,'./type')
           #data['Module Serial Number'] = module_sn
           module_info.append("Modules",data,'{}-{}'.format(module_sn,slot))
    else:
        data = OrderedDict()
        data["Error"] = Formatter.add_marker('Command {} is invalid, no output received. Please check command logs for further information.'.format(show_inventory['command']), Marker.WARNING)
        module_info.append("Modules", data, 'error')

def process_license_for_all(report, show_license_usage):
    Logger.info('Inside process_license_for_all')
    license_info = report.add_section("Licenses",'license')
    license_info['License type'] = Formatter.add_marker('Traditional', Marker.INFO)
    if "success" in show_license_usage["status"]:
        content = getxmltree(show_license_usage['response'],'__readonly__')
        rows = getxmlrows(content,'./TABLE_show_lic_usage/ROW_show_lic_usage')
        for row in rows:
            feature=getnodevalue(row,'./feature_name')
            expiry_date = getnodevalue(row,'./expiry_date')
            data = OrderedDict()
            data['Feature'] = feature
            data['Installed'] = getnodevalue(row,'./lic_installed')
            data['Count'] = getnodevalue(row,'./count')
            data['Status'] = getnodevalue(row,'./status')
            data['Expiry date'] = expiry_date if expiry_date is not None else '-'
            data['Comments'] = getnodevalue(row,'./comments')
            license_info.append("Licenses", data, feature)
    else:
        data = OrderedDict()
        data["Error"] = Formatter.add_marker('Command {} is invalid, no output received. Please check command logs for further information.'.format(show_license_usage['command']), Marker.WARNING)
        license_info.append("Licenses", data, 'error')

def process_license_for_n5k(report, show_license_usage):
    Logger.info('Inside process_license_for_n5k')
    license_info = report.add_section("Licenses",'license')
    license_info['License type'] = Formatter.add_marker('Traditional', Marker.INFO)
    if "success" in show_license_usage["status"]:
        content = getxmltree(show_license_usage['response'],'__readonly__')
        rows = getxmlrows(content,'./TABLE_lic_usage/ROW_lic_usage')
        for row in rows:
            data = OrderedDict()
            feature=getnodevalue(row,'./feature_name')
            expiry_date = getnodevalue(row,'./expiry')
            data['Feature'] = feature
            data['Installed'] = getnodevalue(row,'./install_status')
            data['Count'] = getnodevalue(row,'./lic_count')
            data['Status'] = getnodevalue(row,'./status')
            data['Expiry date'] = expiry_date if expiry_date is not None else '-'
            data['Comments'] = getnodevalue(row,'./comments')
            license_info.append("Licenses",data,feature)
    else:
        data = OrderedDict()
        data["Error"] = Formatter.add_marker('Command {} is invalid, no output received. Please check command logs for further information.'.format(show_license_usage['command']), Marker.WARNING)
        license_info.append("Licenses", data, 'error')

def process_smart_license(report, show_license_usage):
    Logger.info('Inside process_smart_license')
    license_info = report.add_section("Licenses",'license')
    license_info['License type'] = Formatter.add_marker('Smart', Marker.INFO)
    if "success" in show_license_usage["status"]:
        content = getxmltree(show_license_usage['response'],'__readonly__')
        rows = getxmlrows(content,'./TABLE_show_smart_lic_usage/ROW_show_smart_lic_usage')
        for row in rows:
            data = OrderedDict()
            feature=getnodevalue(row,'./smart_feature_name')
            count = getnodevalue(row,'./smart_count')
            version = getnodevalue(row,'./smart_version')
            status = getnodevalue(row,'./smart_status')
            data['Feature'] = feature
            data['Version'] = version
            data['Count'] = count
            data['Status'] = status
            license_info.append("Licenses",data,feature)
        
##
