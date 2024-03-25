from burp import IBurpExtender
from burp import IMessageEditorTab
from burp import IMessageEditorTabFactory
from hl7apy.parser import parse_message
from hl7apy.exceptions import UnsupportedVersion
import json
import sys

class BurpExtender(IBurpExtender, IMessageEditorTabFactory):
    def registerExtenderCallbacks(self, callbacks):
        self._callbacks = callbacks

        self._helpers = callbacks.getHelpers()

        callbacks.setExtensionName("HL7Magic")

        callbacks.registerMessageEditorTabFactory(self)

        sys.stdout = callbacks.getStdout()
        sys.stderr = callbacks.getStderr()

    
    def createNewInstance(self, controller, editable):

        return HL7ConverterTab(self, controller, editable, self._callbacks)
    
        
class HL7ConverterTab(IMessageEditorTab):

    def __init__(self, extender, controller, editable, callbacks):
        self._extender = extender
        self.controller = controller
        self.editable = editable
        self._editor = callbacks.createTextEditor()
        self._helpers = extender._helpers
        self.req = None


    def getTabCaption(self):

        return "HL7Magic"

    def getUiComponent(self):

        return self._editor.getComponent()
    
    def isEnabled(self, content, isRequest):
        if isRequest and content:
            return True
        return False
    
  
    def setMessage(self, content, isRequest):
        if content is None:
            self._editor.setText(None)
            self._editor.setEditable(False)
        else:
            self.req = self._helpers.analyzeRequest(content)
            params  = content[(self.req.getBodyOffset()):].tostring()
            json_data = self.hl72json(params)
            self._editor.setText(json_data)
            self._editor.setEditable(True)

    
    def getMessage(self): 
        message = self._editor.getText()
        hl7_message = self.json2hl7(message)

        return self._helpers.buildHttpMessage(self.req.getHeaders(), hl7_message)


    def getSelectedData(self):
        return self._editor.getSelectedText()

    def isModified(self):
        return self._editor.isTextModified()
    

    def hl72json(self, message):
            
            try:
                self.m = parse_message(message.replace("\n", "\r"), find_groups=False)

            except Exception as e:
                print("Error", e)
                
            seg_list = []

            result = {
                "messageType": "",
                "segments": []
            }

            for seg in self.m.children:
                seg_list.append(seg.name)

            for segName in set(seg_list):

                if len(getattr(self.m, segName)) > 1:
                    multi_segs = []
                    for i, subSeg in enumerate(getattr(self.m, segName)):
                        segment_name = subSeg.name
                        current_segment = {
                            "name": segment_name,
                            "fields": []
                        }

                        for f in getattr(self.m, segName)[i].children:
                            field_data = {
                                "short_name": f.name,
                                "long_name": f.long_name,
                            }

                            if len(getattr(getattr(self.m, segName)[1], f.name)) > 1:
                                subfields = []
                                for v in getattr(getattr(self.m, segName)[i], f.name):
                                    subfields.append(v.value)
                                    field_data.update({"value": subfields})
                            else:
                                field_data.update({"value": f.value})
                                

                            current_segment["fields"].append(field_data)
                            
                            
                        multi_segs.append(current_segment)
                            
                        

                    result["segments"].append(multi_segs)

                
                else:
                    segment_name = segName
                    current_segment = {
                        "name": segment_name,
                        "fields": []
                    }
                    if current_segment is not None:
                        for f in getattr(self.m, segName).children:
                            field_data = {
                                "short_name": f.name,
                                "long_name": f.long_name,
                            }

                            if len(getattr(getattr(self.m, segName), f.name)) > 1:
                                subfields = []
                                for v in getattr(getattr(self.m, segName), f.name):
                                    subfields.append(v.value)
                                    field_data.update({"value": subfields})
                            else:
                                field_data.update({"value": f.value})

                            current_segment["fields"].append(field_data)
                        


                    result["segments"].append(current_segment)

            d = json.dumps(result, indent=4)

            output_body = bytes(d)

            return output_body


    def json2hl7(self, json_message):
        d = self._helpers.bytesToString(json_message)
        result = eval(d)


        for s in result['segments']:
            if isinstance(s, list):
                for i, item in enumerate(s):
                    for field_data in item['fields']:
                        if isinstance(field_data['value'], list):
                            for j, value in enumerate(field_data['value']): 
                                getattr(getattr(self.m, item['name'])[i], field_data['short_name'])[j].value = value
                        else:
                            setattr(getattr(self.m, item['name'])[i], field_data['short_name'], field_data['value'])
            else:
                for field_data in s['fields']:
                    if isinstance(field_data['value'], list):
                        for i, value in enumerate(field_data['value']):
                            getattr(getattr(self.m, s['name']), field_data['short_name'])[i].value = value
                    else:
                        setattr(getattr(self.m, s['name']), field_data['short_name'], field_data['value'])

                

        amended = self.m.to_er7().replace("\r", "\n")

        return amended
