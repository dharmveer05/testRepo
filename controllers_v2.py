# -*- coding: utf-8 -*-

import hashlib
import json
import re
import traceback
import time
from time import sleep
from config import Production
from urllib.request import urlopen
import dateparser
import requests
from flask import Blueprint, abort, request, session, Response
from jinja2 import Environment, PackageLoader, Template, select_autoescape
from bson.json_util import dumps
from bson.objectid import ObjectId
from app import app
from app.botagents.models import Bot, CubeSchemaConfiguration, CubeColumnConfiguration
from app.conversation.models import History
from app.conversation.models import SessionVariable, ChatMessages, AccountSaved, FollowerList, PopularList, Comment
from app.intents.models import ApiStatusResponse
from app.commons import build_response
from app.endpoint.utils import (SilentUndefined, call_api, customDateFilter,
                                customDateFormatFilter,
                                customOnlyDateFormatFilter, dateDiffFilter,
                                get_synonyms, split_sentence,
                                validateUserInput, randomString, setSessionKey, getSessionKey, rename_resource_label, register_account, delete_Accounts, register_account_azure, delete_cluster_instance)
from app.endpoint.webscoket_io import created_jira_instance
from app.intents.models import Intent
from app.nlu.classifiers.intent_classifier_tf2 import EmbeddingIntentClassifierTF2
from app.nlu.entity_extractor import EntityExtractor
from app.nlu.tasks import model_updated_signal
import pymongo
from bson.json_util import loads
from app.commons.utils import update_document
from app.api_logs.models import CatalogFile
import random
import sys
import importlib
from app.endpoint.helpers import (isValidProductVersion, save_chat_messages)
from flask import Flask, flash, request, redirect, render_template, jsonify
from werkzeug.utils import secure_filename
import urllib.request
import os
from pathlib import Path
from mongoengine.queryset.visitor import Q
from app.api_logs.models import ModelConfiguration, ServiceConfiguration, AppConfiguration, AdminConfiguration, MessageConfiguration
from flask import send_from_directory, send_file
from datetime import datetime
import pytz
from app.login.models import AccountUser
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg2
from app.botagents.models import ThemeConfig, AboutUs
from datetime import date
from datetime import time
from flask_mail import Mail, Message
import xlwt
from xlwt import Workbook
from collections import namedtuple
import random
import math
import string
from hashlib import sha256
import pdfkit
from random import randint
from app.helpers.db.SQLHelpers import SQLHelpers
import re
import shutil
import csv
from app.search.helpers import indexEntityDoc, indexItems, indexItemAttachmentDocs, indexCollectionAttachmentDocs, deleteEntityDoc
from app.helpers.aws.s3_helpers import S3Client
import mimetypes

if sys.version_info[0] >= 3:
    unicode = str

endpointV2 = Blueprint('apiv2', __name__, url_prefix='/api')
app1 = Flask(__name__)

mail = Mail(app1)
# configuration of mail
app1.config['MAIL_SERVER'] = 'mail.privateemail.com'
app1.config['MAIL_PORT'] = 465
app1.config['MAIL_USERNAME'] = 'team@istoria.ai'
app1.config['MAIL_PASSWORD'] = 'Sunset#today2'
app1.config['MAIL_USE_TLS'] = False
app1.config['MAIL_USE_SSL'] = True
mail = Mail(app1)

mailSender = "team@istoria.ai"

sentence_classifier = None
synonyms = None
bot_conversation = ""
entity_extraction = None
speech_response = ""
chat_list = []
previous_session_id = ""
index = 0
processorNamePattern = re.compile(r'(?<!^)(?=[A-Z])')

ES_SYNC_ON = app.config.get('ES_AUTO_SYNC')

'''
jinjaenv = Environment(
    loader=PackageLoader('app.endpointV2', 'templates'),
    autoescape=select_autoescape(
    enabled_extensions=('html', 'xml'),
    default_for_string=True,
    default=True)
)
jinjaenv.filters['customDateFilter'] = customDateFilter
'''

# Request Handler


@endpointV2.route('/v2', methods=['POST'])
def api():
    app.logger.info("api/v2 called")
    """
    EndpointV2 to converse with chatbot.
    Chat context is maintained by exchanging the payload between client and bot.

    sample input/output payload =>

    {
      "currentNode": "",
      "complete": false,
      "parameters": [],
      "extractedParameters": {},
      "missingParameters": [],
      "intent": {
      },
      "context": {},
      "input": "hello",
      "speechResponse": [
      ],
      "prevIntents": {

      }
    }

    :param json:
    :return json:
    """
    request_json = request.get_json(silent=True)
    result_json = request_json
    sessionChatId = "-1"
    if('cookie_session' not in session):
        sessionCookieID = randomString()
        app.logger.info(
            "GENERATING SESSION ID FOR STATUS API:: %s", sessionCookieID)
        session['cookie_session'] = randomString()
    # if('login_result' not in session):
    #     login_user('deepak', 'deepak123')
    if request_json:
        app.logger.info("request_json.get %s", request_json.get("input"))
        sessionChatId = request_json.get("chatId")
        session_params = {}
        for key in session.keys():
            session_params[key] = session[key]
        context = {"context": request_json["context"],
                   "session": session_params, "chatId": request_json["chatId"]}
        app.logger.info("session details :: %s", request_json["context"])
        template = Template("", undefined=SilentUndefined)
        template.environment.filters['customDateFilter'] = customDateFilter
        template.environment.filters['dateDiffFilter'] = dateDiffFilter
        template.environment.filters['customDateFormatFilter'] = customDateFormatFilter
        template.environment.filters['customOnlyDateFormatFilter'] = customOnlyDateFormatFilter
        template.environment.filters['rename_resource_label'] = rename_resource_label
        template.environment.filters['register_account'] = register_account
        template.environment.filters['register_account_azure'] = register_account_azure
        template.environment.filters['delete_Accounts'] = delete_Accounts
        template.environment.filters['delete_cluster_instance'] = delete_cluster_instance
        template.environment.filters['randomString'] = randomString
        template.globals['created_jira_instance'] = created_jira_instance
        template.globals['setSessionKey'] = setSessionKey
        template.globals['getSessionKey'] = getSessionKey
        app.logger.info(
            "DEFAULT_WELCOME_INTENT_NAME TEMPLATE ENVIRONMENT:: %s", template.environment.__dict__)
        if app.config["DEFAULT_WELCOME_INTENT_NAME"] in request_json.get("input"):
            intent = Intent.objects(
                intentId=request_json.get("input")).first()
            app.logger.info("WELCOME INTENT :: %s", intent.intentId)
            result_json["complete"] = True
            result_json["intent"]["object_id"] = str(intent.id)
            result_json["intent"]["id"] = str(intent.intentId)
            result_json["input"] = request_json.get("input")
            template = Template(
                intent.prompt,
                undefined=SilentUndefined)
            template.environment.filters['customDateFilter'] = customDateFilter
            template.environment.filters['dateDiffFilter'] = dateDiffFilter
            template.environment.filters['customDateFormatFilter'] = customDateFormatFilter
            template.environment.filters['customOnlyDateFormatFilter'] = customOnlyDateFormatFilter
            template.environment.filters['created_jira_instance'] = created_jira_instance
            template.environment.filters['randomString'] = randomString
            result_json["speechResponse"] = split_sentence(
                template.render(**context))
            save_chat_messages(sessionChatId, 'Bot', request_json, result_json)
            app.logger.info(request_json.get("input"), extra=result_json)
            return build_response.build_json(result_json)
        intent_id, confidence, suggestions = predict(request_json.get("input"))
        app.logger.info("intent_id => %s, confidence=> %s, input=> %s",
                        intent_id, confidence, request_json.get("input"))

        intent = Intent.objects.get(intentId=intent_id)
        save_chat_messages(sessionChatId, 'User', request_json, result_json)

        if(intent.dependsOn):
            app.logger.info("INTENT_DEPENDS_ON --> %s",
                            request_json.get("completed_intents"))
            if(request_json.get("completed_intents") != None and intent.dependsOn not in request_json.get("completed_intents")):
                result_json["backIntents"].append(intent.intentId)
                result_json["prevInput"] = request_json.get("input")
                intent = Intent.objects.get(intentId=intent.dependsOn)

        if intent.parameters:
            parameters = intent.parameters
        else:
            parameters = []

        # IF PREVIOUS INTENT COMPLETED, THEN SWITCH FOR NEW
        app.logger.info("if 183 ==> %s", request_json)
        if ((request_json.get("complete") is None) or (
                request_json.get("complete") is True)):
            result_json["intent"] = {
                "object_id": str(intent.id),
                "confidence": confidence,
                "id": str(intent.intentId)
                # "id": str(intent.intentId.encode('utf8'))
            }

            if parameters:
                # Extract NER entities
                # extracted_parameters = entity_extraction.predict(intent_id, request_json.get("input"))
                extracted_parameters = entity_extraction.predictMultiAttr(
                    intent_id, request_json.get("input"))
                app.logger.info("extracted_parameters: %s",
                                extracted_parameters)

                missing_parameters = []
                result_json["missingParameters"] = []
                result_json["extractedParameters"] = {}
                result_json["parameters"] = []
                result_json["optionButtons"] = []
                for parameter in parameters:
                    result_json["parameters"].append({
                        "name": parameter.name,
                        # "type": parameter.type,
                        # "required": parameter.required,
                        # response Type added
                        "responseType": parameter.responseType,
                        "option": parameter.options,
                        "failureMessage": parameter.failureMessage,
                        "successMessage": parameter.successMessage
                    })
                    result_json["optionButtons"].append({
                        "option": parameter.options,
                        "failureMessage": parameter.failureMessage,
                        "successMessage": parameter.successMessage,
                    })
                    if parameter.required:
                        app.logger.info(
                            "parameter.name 221 --> %s", parameter.name)
                        if (("details_confirm" == parameter.name or "confirm_wait" == parameter.name
                                or "delete_confirm" == parameter.name)
                                and ("commandIntents" in request_json and len(request_json["commandIntents"]) > 0)):
                            app.logger.info(
                                "parameter.name::  %s", parameter.name)
                            continue

                        elif parameter.name not in extracted_parameters.keys():
                            result_json["missingParameters"].append(
                                parameter.name)
                            missing_parameters.append(parameter)

                    app.logger.info("extracted_parameters  :: %s",
                                    extracted_parameters.values())

                    if parameter.name in extracted_parameters.keys():
                        if hasattr(parameter, 'isProcessorHandler') and parameter.isProcessorHandler:
                            processorFile = processorNamePattern.sub(
                                '_', parameter.processorHandlerFileName).lower()
                            processor = importlib.import_module(
                                'app.processors.'+processorFile)
                            processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                           'intentId': intent.intentId, 'intent': intent}
                            validated, extractedParams = processor.processIntentEntity(
                                **processArgs)
                            extracted_parameters[parameter.name] = extractedParams[parameter.name]
                            if not validated:
                                result_json["missingParameters"].append(
                                    parameter.name)
                                missing_parameters.append(parameter)
                        # else:
                        #     app.logger.info("extracted_parameters is datetime:: %s", extracted_parameters)
                        #     extracted_parameters[parameter.name] = str(
                        #         dateparser.parse(extracted_parameters[parameter.name]))

                result_json["extractedParameters"] = extracted_parameters
                app.logger.info("extracted_parameters 111111  :: %s",
                                result_json["extractedParameters"])
                app.logger.info("missing_parameters after complete true:: %s, %s",
                                missing_parameters, result_json["missingParameters"])
                # IF NEW INTENT HAVE PARAMETERS THEN SET COMPLETE TO FALSE AGAIN TO START NEW INTENT
                # AND MOVE TO NODE FOR MISSING PARAMETER FIELD OF NEW INTENT
                if missing_parameters:
                    result_json["complete"] = False
                    current_node = missing_parameters[0]
                    result_json["currentNode"] = current_node["name"]

                    if hasattr(current_node, 'isProcessorHandler') and current_node.isProcessorHandler:
                        processorFile = processorNamePattern.sub(
                            '_', current_node.processorHandlerFileName).lower()
                        processor = importlib.import_module(
                            'app.processors.'+processorFile)
                        processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                       'intentId': intent.intentId, 'currentNode': current_node, 'intent': intent}
                        processorResponse = processor.responseHandler(
                            **processArgs)
                    else:
                        session_params = {}
                        for key in session.keys():
                            session_params[key] = session[key]

                        context = {"parameters": extracted_parameters,
                                   "context": request_json["context"],
                                   "chatId": request_json["chatId"],
                                   "session": session_params}
                        template = Template(
                            current_node["prompt"], undefined=SilentUndefined)
                        render_template_result = template.render(**context)
                        app.logger.info(
                            "CALL CHECK DIALOGUE CHANGE:: 199 %s", context)
                        result_json = checkDialogueChange(
                            render_template_result, result_json, request_json)
                    #result_json["speechResponse"] = split_sentence(render_template_result)
                    result_json["option"] = current_node["options"]
                    result_json["successMessage"] = current_node["successMessage"]
                    result_json["failMessage"] = current_node["failureMessage"]
                else:
                    result_json["complete"] = True
                    if request_json["completed_intents"] is not None:
                        result_json["completed_intents"] = request_json["completed_intents"].append(
                            intent.intentId)
                    else:
                        result_json["completed_intents"] = [intent.intentId]
                    context["parameters"] = extracted_parameters

                app.logger.info("missing_parameters AFTER PROCESSORS complete true:: %s, %s",
                                missing_parameters, result_json["missingParameters"])
                if len(result_json["missingParameters"]) <= 0:
                    result_json["complete"] = True
                    if request_json["completed_intents"] is not None:
                        result_json["completed_intents"] = request_json["completed_intents"].append(
                            intent.intentId)
                    else:
                        result_json["completed_intents"] = [intent.intentId]

            else:
                result_json["complete"] = True
                if request_json["completed_intents"] is not None:
                    result_json["completed_intents"] = request_json["completed_intents"].append(
                        intent.intentId)
                else:
                    result_json["completed_intents"] = [intent.intentId]

            # *********EXECUTE PRECONDITIONS HERE**********************

        # IF NOT COMPLETED, THEN DO NOT SWITCH THE INTENT BEFORE
        # AND GET THE CURRENT INTENT FROM REQUEST 'intent' OBJECT FIELD
        elif request_json.get("complete") is False:

            if "cancel" not in intent.name:
                app.logger.info("elif 294 ==> %s",
                                request_json["intent"]["id"])
                intent_id = request_json["intent"]["id"]
                intent = Intent.objects.get(intentId=intent_id)

                # VALIDATE USER INPUTS
                current_node = [
                    node for node in intent.parameters if request_json.get("currentNode") in node.name][0]

                # CHECK FOR NER, SYNONYMS FOR PARAMETERS
                if hasattr(current_node, 'isProcessorHandler') and current_node.isProcessorHandler:
                    processorFile = processorNamePattern.sub(
                        '_', current_node.processorHandlerFileName).lower()
                    processor = importlib.import_module(
                        'app.processors.'+processorFile)
                    processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                   'intentId': intent.intentId, 'currentNode': current_node, 'intent': intent}
                    validated, extracted_parameter = processor.processInputEntity(
                        **processArgs)
                    if not validated:
                        result_json["missingParameters"].insert(
                            0, current_node.name)
                else:
                    extracted_parameter = entity_extraction.replace_synonyms({
                        request_json.get("currentNode"): request_json.get("input")
                    })

                # else:
                #     extracted_parameter = entity_extraction.without_replace_synonym({
                #         request_json.get("currentNode"): request_json.get("input") })

                app.logger.info(request_json.get("currentNode"))
                app.logger.info(
                    "extracted_parameter replace_synonyms:: %s", extracted_parameter)
                # app.logger.info("extracted_parameter Keys:: %s", extracted_parameter.keys())
                app.logger.info("completed_intents:: %s",
                                request_json["completed_intents"])

                app.logger.info("CURRENT NODE VALIDATION:: %s, %s",
                                current_node["validationRequired"], current_node["validationFailureResponse"])

                if(current_node["validationRequired"]):
                    isValidInput = validateUserInput(request_json.get("input"),
                                                     current_node["validationType"])

                    app.logger.info("IS VALID INPUT:: %s", isValidInput)
                    # IF VALIDATION FAILED, PREPARE FAILURE RESPONSE AND RETURN
                    if(isValidInput is False):
                        session_params = {}
                        for key in session.keys():
                            session_params[key] = session[key]
                        context = {"parameters": {param for param in result_json["extractedParameters"]}.update(extracted_parameter),
                                   "context": request_json["context"],
                                   "chatId": request_json["chatId"],
                                   "session": session_params}
                        template = Template(
                            current_node["validationFailureResponse"], undefined=SilentUndefined)
                        render_template_result = template.render(**context)
                        app.logger.info("CALL CHECK DIALOGUE CHANGE:: 315")
                        result_json = checkDialogueChange(
                            render_template_result, result_json, request_json)
                        if intent.id != result_json["intent"]["id"]:
                            intent = Intent.objects.get(
                                intentId=result_json["intent"]["id"])

                        # RETURN FINAL RESPONSE FROM HERE IF VALIDATION FAILED
                        save_chat_messages(
                            sessionChatId, 'Bot', request_json, result_json)
                        return build_response.build_json(result_json)

                app.logger.info("CURRENT NODE :: %s",
                                request_json.get("currentNode"))
                app.logger.info("extracted_parameter 324 :: %s",
                                extracted_parameter)
                result_json["extractedParameters"].update(extracted_parameter)
                result_json["missingParameters"].remove(
                    request_json.get("currentNode"))

                # IF ALL PARAMETERS ARE EXTRACTED THEN COMPLETE INTENT
                if len(result_json["missingParameters"]) == 0:
                    app.logger.info("NO MISSING PARAMETERS LEFT")
                    result_json["complete"] = True
                    # result_json["completed_intents"].append(intent.intentId)
                    app.logger.info(
                        "completed_intents AFTER complete=true:: %s", result_json["completed_intents"])
                    context = {"parameters": result_json["extractedParameters"], "chatId": request_json["chatId"],
                               "context": request_json["context"]}

                elif (("details_confirm" == result_json["missingParameters"][0] or "confirm_wait" == result_json["missingParameters"][0]
                        or "delete_confirm" == result_json["missingParameters"][0])
                        and ("commandIntents" in request_json and len(request_json["commandIntents"]) > 0)):
                    app.logger.info("DETAILS_CONFIRM --> %s",
                                    result_json["missingParameters"][0])
                    result_json["missingParameters"] = []
                    result_json["complete"] = True
                    result_json["speechResponse"] = ""

                # ELSE CONTINUE CURRENT INTENT MISSING PARAMETER AND MOVE TO NEXT NODE
                else:
                    missing_parameter = result_json["missingParameters"][0]
                    app.logger.info(
                        "MISSING PARAMETERS CONTINUES: %s", missing_parameter)
                    result_json["complete"] = False
                    # missingParamNodes = [
                    #     node for node in intent.parameters if missing_parameter in node.name]
                    #current_node = missingParamNodes[0]
                    current_node = [
                        node for node in intent.parameters if missing_parameter in node.name][0]
                    result_json["currentNode"] = current_node.name
                    app.logger.info(
                        "CURRENT NODE IN ELSE :: %s", current_node.name)
                    # IF RESPONSE TYPE IS API
                    if current_node["responseType"] == 'api':
                        isJson = False
                        parameters = result_json["extractedParameters"]
                        context["parameters"] = parameters
                        app.logger.info("parameters:: %s", parameters)
                        app.logger.info("Request Cookies %s" % request.cookies)
                        headers = current_node.get_headers()
                        cookieHeader = ""
                        app.logger.info(
                            "session before calling refresh token :: %s", session)
                        if 'login_result' in session and session['login_result']['access_token']:
                            refresh_token()

                        if(sys.version_info[0] < 3):
                            for ckey, cvalue in request.cookies.iteritems():
                                cookieHeader += ckey+"="+cvalue+";"
                        else:
                            for ckey, cvalue in request.cookies.items():
                                cookieHeader += ckey+"="+cvalue+";"

                        headers['Cookie'] = cookieHeader
                        app.logger.info("headers %s" % headers)
                        rendered_headers = headers
                        session_params = {}
                        for key in session.keys():
                            session_params[key] = session[key]
                        context["session_params"] = session_params
                        for header_key in headers.keys():

                            headers_value_template = Template(
                                headers[header_key], undefined=SilentUndefined)
                            rendered_header_val = headers_value_template.render(
                                **context)
                            app.logger.info(
                                "HEADER KEY IN FOR LOOP 1 :: %s", headers_value_template)
                            app.logger.info(
                                "HEADER KEY IN FOR LOOP 2 :: %s", rendered_header_val)
                            app.logger.info(
                                "HEADER KEY IN FOR LOOP 3 :: %s", context)
                            rendered_headers[header_key] = rendered_header_val

                        app.logger.info("header value :: %s", rendered_headers)
                        url_template = Template(
                            current_node["url"], undefined=SilentUndefined)
                        rendered_url = url_template.render(**context)

                        if current_node["isJson"]:
                            isJson = True
                            context["parameters"] = result_json["extractedParameters"]
                            app.logger.info("context:: %s", context)
                            app.logger.info(
                                "API requestPayload:: %s", current_node["requestPayload"])
                            request_template = Template(
                                current_node["requestPayload"], undefined=SilentUndefined)
                            app.logger.info(
                                "request_template:: %s", request_template)
                            parameters = json.loads(
                                request_template.render(**context))
                        try:
                            result = call_api(rendered_url,
                                              current_node["requestType"], rendered_headers,
                                              parameters, isJson)

                            session[current_node.name] = result
                            session_params = {}
                            for key in session.keys():
                                session_params[key] = session[key]
                            context["session_params"] = session_params
                            app.logger.info(
                                "SESSION AFTER CALL API:: %s", session)
                            template = Template(
                                current_node.prompt, undefined=SilentUndefined)
                            render_template_result = template.render(**context)
                            app.logger.info(
                                "CALL CHECK DIALOGUE CHANGE:: 366 %s", render_template_result)
                            result_json = checkDialogueChange(
                                render_template_result, result_json, request_json)
                            if intent.id != result_json["intent"]["id"]:
                                intent = Intent.objects.get(
                                    intentId=result_json["intent"]["id"])

                            app.logger.info("API result :: %s", result)
                        except Exception as e:
                            app.logger.info(traceback.format_exc())
                            app.logger.warn("API call failed %s", e)
                            result_json["speechResponse"] = [
                                "Sorry, I can't connect to the service at this moment. Please try again later."]
                        # else:
                        #     app.logger.info("API intent speechResponse: %s", current_node.prompt)
                        #     app.logger.info(" Type of result %s", type(result))

                        #     if isinstance(result, unicode):
                        #         context["result"] = json.loads(result)
                        #     else:
                        #         context["result"] = result

                        #     app.logger.info("API INSIDE ELSE 1: %s", context)
                        #     template = Template(current_node.prompt, undefined=SilentUndefined)
                        #     result_json["speechResponse"] = split_sentence(template.render(**context))

                    # IF PROCESSOR ASSOCIATED
                    elif hasattr(current_node, 'isProcessorHandler') and current_node.isProcessorHandler:
                        app.logger.info("PROCESSOR RESPONSE NODE HANDLER:: ")
                        processorFile = processorNamePattern.sub(
                            '_', current_node.processorHandlerFileName).lower()
                        processor = importlib.import_module(
                            'app.processors.'+processorFile)
                        processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                       'intentId': intent.intentId, 'currentNode': current_node, 'intent': intent}
                        handlerSpeechResponse = processor.responseHandler(
                            **processArgs)

                    # IF RESPONSE TYPE IS PROMPT
                    else:
                        app.logger.info("session access token :: %s",
                                        session.get('access_token'))
                        app.logger.info("current node :: %s",
                                        result_json["currentNode"])
                        result_json["currentNode"] = current_node.name
                        context["parameters"] = result_json["extractedParameters"]
                        session_params = {}
                        for key in session.keys():
                            session_params[key] = session[key]
                        context["session_params"] = session_params
                        template = Template(
                            current_node.prompt, undefined=SilentUndefined)
                        result_json["speechResponse"] = split_sentence(
                            template.render(**context))
            else:
                result_json["currentNode"] = None
                result_json["missingParameters"] = []
                result_json["parameters"] = {}
                result_json["intent"] = {}
                result_json["complete"] = True
                result_json["completed_intents"] = []
                result_json["backIntents"] = []

        if result_json["complete"]:
            context["result"] = {}
            context["parameters"] = result_json["extractedParameters"]
            session_params = {}
            for key in session.keys():
                session_params[key] = session[key]
            context["session_params"] = session_params
            app.logger.info("INTENT:: %s", intent)
            if hasattr(intent, 'finalResponseType') and intent.finalResponseType == 'handler':
                app.logger.info("INTENT PROCESSOR RESPONSE HANDLER:: ")
                processorFile = processorNamePattern.sub(
                    '_', intent.finalResponseHandlerFileName).lower()
                processor = importlib.import_module(
                    'app.processors.'+processorFile)
                processArgs = {'resultJson': result_json, 'requestJson': request_json,
                               'intentId': intent.intentId, 'currentNode': current_node, 'intent': intent}
                handlerSpeechResponse = processor.intentResponseHandler(
                    **processArgs)
            else:
                if "command_runner_intent" in intent.intentId:
                    commandIntents = []
                    scriptFileName = result_json["extractedParameters"]["jet_file_name"]
                    # folderUserName = session['user_name']
                    app.logger.info("scriptFileName --> %s", scriptFileName)
                    folderUserName = getUsernameForPublic(scriptFileName)

                    filepath = r''+app.config['UPLOAD_FOLDER'] + \
                        folderUserName+"/"+scriptFileName.lower()
                    with open(filepath) as fp:
                        line = fp.readline()
                        cnt = 1
                        commandText = ''
                        while line:
                            print("Line {}: {}".format(cnt, line.strip()))
                            fileLine = line.strip()
                            if(fileLine == "" or fileLine.startswith("//") or fileLine.startswith("#")):
                                line = fp.readline()
                                cnt += 1
                                continue
                            commandText += line.strip()+" "
                            # print("commandText {} ".format(commandText1))
                            line = fp.readline()
                            cnt += 1
                        # if(commandText == "" or commandText.startswith("//") or commandText.startswith("#")):
                        #         continue
                        # intent_id, confidence, suggestions = predict(commandText)
                        # app.logger
                        commandsArr = commandText.split(";")
                        for lineCommand in commandsArr:
                            lineCommand = lineCommand.strip()
                            if(lineCommand != "" and not lineCommand.startswith("//") and not lineCommand.startswith("#")):
                                commandIntents.append(
                                    {'commandText': lineCommand, 'isCompleted': False, 'status': "notstarted"})

                    app.logger.info("commandIntents::  %s", commandIntents)
                    result_json["commandIntents"] = commandIntents

                template = Template(intent.speechResponse,
                                    undefined=SilentUndefined)
                result_json["speechResponse"] = split_sentence(
                    template.render(**context))
        # RETURN FINAL JSON RESPONSE
        save_chat_messages(sessionChatId, 'Bot', request_json, result_json)
        return build_response.build_json(result_json)
    else:
        return abort(400)


def update_model(app, message, **extra):
    """
    Signal hook to be called after training is completed.
    Reloads ml models and synonyms.
    :param app:
    :param message:
    :param extra:
    :return:
    """
    global sentence_classifier

    sentence_classifier = EmbeddingIntentClassifierTF2.load(
        app.config["MODELS_DIR"], app.config["USE_WORD_VECTORS"])

    synonyms = get_synonyms()

    global entity_extraction

    entity_extraction = EntityExtractor(synonyms)

    app.logger.info("Intent Model updated")


with app.app_context():
    update_model(app, "Models updated")

model_updated_signal.connect(update_model, app)


def get_entity_extraction():
    return entity_extraction


def get_sentence_classifier():
    return sentence_classifier


def predict(sentence):
    """
    Predict Intent using Intent classifier
    :param sentence:
    :return:
    """
    bot = Bot.objects.get(name="default")
    predicted, intents = sentence_classifier.process(sentence)
    app.logger.info("predicted intent %s", predicted)
    if predicted["confidence"] < bot.config.get("confidence_threshold", .90):
        intents = Intent.objects(
            intentId=app.config["DEFAULT_FALLBACK_INTENT_NAME"])
        intents = intents.first().intentId
        return intents, 1.0, []
    else:
        return predicted["intent"], predicted["confidence"], intents[1:]


def place_lat_long():
    try:
        if session['user_latlong']["lat"] == None or session['user_latlong']["lng"] == None:
            print("user_latlong not found")
    except:
        return "Location not found"
    else:
        lat = session['user_latlong']["lat"]
        lon = session['user_latlong']["lng"]
        url = "https://maps.googleapis.com/maps/api/geocode/json?"
        url += "latlng=%s,%s&sensor=false&key=AIzaSyDVEIKaK102vtMzmyUpferEXm6tXBY-rS0" % (
            lat, lon)
        v = urlopen(url).read()
        j = json.loads(v)
        components = j['results'][0]['address_components']
        country = town = None
        for c in components:
            if "country" in c['types']:
                country = c['long_name']
            if "locality" in c['types']:
                town = c['long_name']
        return town


def check(email):
    regex = '^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$'
    # pass the regualar expression
    # and the string in search() method
    if(re.search(regex, email)):
        print("valid")
        return "valid"
    else:
        print("invalid")
        return "invalid"


def refresh_token():
    print("refresh token inside endposint controller called ::")
    # try:
    URL1 = app.config["API_BASE_URL"]+"/token/refresh"
    # app.logger.info("refresh token session :: %s",session)
    # app.logger.info("refresh token :: %s",session['login_result']['refresh_token'])
    headers1 = {"Authorization": "Bearer %s" %
                (session['login_result']['refresh_token'])}
    # app.logger.info("refresh_token :: %s",headers1)
    result = requests.post(url=URL1, headers=headers1)
    # app.logger.info("REFRESH RESULT : %s", str(result))
    resp_json = json.loads(str(result.text))
    # app.logger.info("resp_json inside refresh token :: %s",resp_json)
    session['login_result']['access_token'] = resp_json['access_token']
    # except:
    #     print("refresh token api")

    # pastebin_url1 = json.loads(r.text)
    # session['login_result'] = {"access_token":pastebin_url1["access_token"]}


def checkDialogueChange(render_template_result, result_json, request_json):
    app.logger.info("CHECK DIALOGUE CHANGE :: %s", render_template_result)
    session_params = {}
    for key in session.keys():
        session_params[key] = session[key]
    context = {"context": request_json["context"],
               "session": session_params, "chatId": request_json["chatId"]}
    if("$$MOVE_BACK##" in render_template_result or "$$MOVE_TO_DIALOG##" in render_template_result):
        newIntent = None
        templ_result_arr = render_template_result.split("$$")
        if len(templ_result_arr) >= 3:
            render_template_result = templ_result_arr[0] + \
                " "+templ_result_arr[2]
        else:
            render_template_result = templ_result_arr[0]

        tempIntentValArr = templ_result_arr[1].split("##")
        app.logger.info("**** DIALOGUE CHANGE DETECTED ***** %s, %s",
                        tempIntentValArr[0], tempIntentValArr[1])
        if("PREV_INTENT" in tempIntentValArr[1] and len(request_json["backIntents"]) > 0):
            newIntent = Intent.objects.get(
                intentId=request_json["backIntents"].pop())
            result_json["intent"] = {
                "object_id": str(newIntent.id),
                "confidence": 1,
                "id": str(newIntent.intentId)
            }
        elif("PREV_INTENT" not in tempIntentValArr[1]):
            newIntent = Intent.objects.get(intentId=tempIntentValArr[1])
            result_json["intent"] = {
                "object_id": str(newIntent.id),
                "confidence": 1,
                "id": str(newIntent.intentId)
            }
        if newIntent is not None:
            if newIntent.parameters:
                parameters = newIntent.parameters
                if parameters:
                    missing_parameters = []

                    extracted_parameters = entity_extraction.predictMultiAttr(
                        newIntent.intentId, request_json.get("input"))
                    app.logger.info("PREV USER INPUT:: %s",
                                    request_json["prevInput"])
                    if request_json["prevInput"] is not None:
                        prev_extracted_parameters = entity_extraction.predictMultiAttr(
                            newIntent.intentId, request_json["prevInput"])
                        extracted_parameters.update(prev_extracted_parameters)

                    app.logger.info(
                        "Final extracted_parameters in MoveBack:: ", extracted_parameters)

                    if result_json["missingParameters"]:
                        for param in result_json["missingParameters"]:
                            if param not in request_json["extractedParameters"].keys():
                                app.logger.info(
                                    "UPDATING EXTRACT PARAM:: %s", param)
                                result_json["extractedParameters"][param] = ""

                    if result_json["extractedParameters"]:
                        for param in result_json["extractedParameters"]:
                            app.logger.info(
                                "REMOVING PARAM EXTRACTED FOR MISSING:: %s", param)
                            if param in result_json["missingParameters"]:
                                result_json["missingParameters"].remove(param)

                    for parameter in parameters:
                        result_json["parameters"].append({
                            "name": parameter.name,
                            "responseType": parameter.responseType,
                            "option": parameter.options,
                            "failureMessage": parameter.failureMessage,
                            "successMessage": parameter.successMessage
                        })
                        if parameter.required:
                            if parameter.name not in result_json["extractedParameters"].keys():
                                result_json["missingParameters"].append(
                                    parameter.name)
                                missing_parameters.append(parameter)
                            if parameter.name in extracted_parameters.keys():
                                if hasattr(parameter, 'isProcessorHandler') and parameter.isProcessorHandler:
                                    processorFile = processorNamePattern.sub(
                                        '_', parameter.processorHandlerFileName).lower()
                                    processor = importlib.import_module(
                                        'app.processors.'+processorFile)
                                    processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                                   'intentId': newIntent.intentId, 'intent': newIntent}
                                    validated, extractedParams = processor.processIntentEntity(
                                        **processArgs)
                                    extracted_parameters[parameter.name] = extractedParams[parameter.name]
                                    if not validated:
                                        result_json["missingParameters"].append(
                                            parameter.name)
                                        missing_parameters.append(parameter)
                                else:
                                    result_json["extractedParameters"] = extracted_parameters

                    if missing_parameters:
                        result_json["complete"] = False
                        current_node = missing_parameters[0]
                        result_json["currentNode"] = current_node["name"]

                        if hasattr(current_node, 'isProcessorHandler') and current_node.isProcessorHandler:
                            processorFile = processorNamePattern.sub(
                                '_', current_node.processorHandlerFileName).lower()
                            processor = importlib.import_module(
                                'app.processors.'+processorFile)
                            processArgs = {'resultJson': result_json, 'requestJson': request_json,
                                           'intentId': newIntent.intentId, 'currentNode': current_node, 'intent': newIntent}
                            render_template_result = processor.responseHandler(
                                **processArgs)
                        else:
                            context = {"parameters": result_json["extractedParameters"],
                                       "context": request_json["context"],
                                       "chatId": request_json["chatId"],
                                       "session": session}
                            template = Template(
                                current_node["prompt"], undefined=SilentUndefined)
                            render_template_result = template.render(**context)
                    app.logger.info(
                        " CHANGE BACK AGAIN render_template_result:: %s", render_template_result)
    app.logger.info("CHANGE DIALOGUE FINAL RESPONSE:: %s",
                    render_template_result)
    result_json["speechResponse"] = split_sentence(render_template_result)
    return result_json


@endpointV2.route('/v2/status/product', methods=['GET'])
def get_product_status_response():

    resp = {}
    reqChatId = request.args.get('chatId')
    resp["chatId"] = reqChatId
    app.logger.info("API STATUS CHAT ID:: %s", reqChatId)
    apiResponses = ApiStatusResponse.objects(chatId=reqChatId)
    app.logger.info("STATUS API RESPONSE::%s", apiResponses)
    productPort = ""
    productType = ""
    htmlResponse = ""
    isSuccessAny = False
    if apiResponses:
        for apiResponse in apiResponses:
            if(apiResponse is not None and 'confluence' in apiResponse.productName):
                productPort = ":8090"
                productType = "confluence"
            elif(apiResponse is not None and 'bitbucket' in apiResponse.productName):
                productPort = ":7990"
                productType = "bitbucket"
            elif(apiResponse is not None and 'bamboo' in apiResponse.productName):
                productPort = ":8085"
                productType = "bamboo"
            elif(apiResponse is not None and 'jira' in apiResponse.productName):
                productPort = ":8080"
                productType = "jira"

            if(apiResponse is not None and apiResponse.status == 'success'):
                isSuccessAny = True
                app.logger.info("SUCCESS API RESPONSE:: %s",
                                apiResponse.to_json())
                htmlResponse += productType+" (instance name: "+apiResponse.clusterName+", account name: "+apiResponse.account+" ).<br><a href='" + \
                    apiResponse.statusURL+productPort+"' target='_blank'>" + \
                    apiResponse.statusURL+productPort+"</a></b><br><br>"
            else:
                app.logger.info("FAILED API RESPONSE:: %s",
                                apiResponse.to_json())
                htmlResponse += productType+" (instance name: "+apiResponse.clusterName+", account name: " + \
                    apiResponse.account+" ).<br> "+apiResponse.statusURL+" </b><br><br>"

        htmlFinalResponse = "Here is the status of the instance(s) created:###" + \
            htmlResponse
        if isSuccessAny:
            htmlFinalResponse += "###Please note: New URLs may take 1-2 minutes to become active as service is loading."

        resp["speechResponse"] = split_sentence(htmlFinalResponse)
        ApiStatusResponse.objects(chatId=reqChatId).delete()
    else:
        resp["speechResponse"] = []
    app.logger.info("FINAL STATUS RESPONSE:: %s", resp)
    save_chat_messages(reqChatId, 'Bot', {}, resp)
    return build_response.build_json(resp)


@endpointV2.route('/v2/saveConversation/<id>', methods=['PUT'])
def save_conversation(id):
    content = request.get_json(silent=True)
    previous_chat = []
    app.logger.info("Save Conversation :: %s", id)
    timeZ_Kl = pytz.timezone("Asia/Kolkata")
    today = datetime.now(timeZ_Kl)
    save_chat = SessionVariable.objects.get(chatId=str(id))
    previous_chat.extend(save_chat['conversation'])
    previous_chat.extend(content.get('conversation'))
    try:
        save_chat.lastUpdatedTime = today.strftime("%I:%M %p")
        save_chat.lastMessage = content.get("lastMessage")
        save_chat.conversation = previous_chat
        save_chat.save()
    except:
        app.logger.info("Could not saveConversation")
    return jsonify({'code': "200", 'error': 'success'})


@endpointV2.route('/v2/updatePayload/<id>', methods=['PUT'])
def update_payload(id):
    content = request.get_json(silent=True)
    app.logger.info("UPDATE PAYLOAD --> %s", content.get("payload"))
    save_chat = SessionVariable.objects.get(chatId=str(id))
    try:
        save_chat.payload = content.get("payload")
        save_chat.save()
    except:
        app.logger.info("Could not update")
    return "payload_updated"


@endpointV2.route('/v2/clearVariableById/<id>', methods=['PUT'])
def delete_variables_by_id(id):
    save_chat = SessionVariable.objects.get(chatId=str(id))
    try:
        save_chat.conversation = []
        save_chat.lastMessage = ""
        save_chat.save()
    except:
        print("Could not save")
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getChatById/<id>', methods=['GET'])
def read_intent(id):
    return Response(response=dumps(
        SessionVariable.objects.get(
            id=ObjectId(id)).to_mongo().to_dict()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/saveSessionVariable', methods=['POST'])
def save_session_variables():
    timeZ_Kl = pytz.timezone("Asia/Calcutta")
    today = datetime.now(timeZ_Kl)
    content = request.get_json(silent=True)
    app.logger.info("Save Session :: %s", loads(
        request.get_data().decode('utf-8')))
    # try:

    session_variable = SessionVariable()
    session_variable.save()
    app.logger.info("SESSION VAR OBJECT ID::: %s", session_variable.id)
    session_variable.chatId = str(session_variable.id)
    session_variable.sessionName = content.get("session_name")
    session_variable.lastUpdatedTime = today.strftime("%I:%M %p")
    session_variable.lastMessage = content.get("lastMessage")
    session_variable.username = content.get("username")
    # session_variable.payload = content.get("payload")
    session_variable.save()

    app.logger.info("SESSION VAR SAVED:: %s", session_variable)
    # except:
    #     print("Could not save")

    return Response(response=dumps(
        session_variable.to_mongo().to_dict()),
        status=200,
        mimetype="application/json")


def save_history(username):
    # content = request.get_json(silent=True)
    # app.logger.info("save History :: %s",loads(request.get_data().decode('utf-8')))
    # try:
    #     exist = History.objects.get(username= content.get("username"))
    # except Exception:
    history = History()
    history.username = username
    history.save()
    return "history_saved"
    # if exist:
    #     return "history_saved"


@endpointV2.route('/v2/sessionNameExist/<sessionName>', methods=['GET'])
def session_exist(sessionName):
    try:
        exist = SessionVariable.objects.get(sessionName=sessionName)
    except Exception:
        return "false"
    if exist:
        return "true"


@endpointV2.route('/v2/getHistory/<username>', methods=['GET'])
def get_chat_history(username):
    return Response(response=(
        History.objects(
            username=username).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/isAlreadyLogin', methods=['GET'])
def already_login():
    app.logger.info("Session %s", session)
    if session != None and 'login_result' in session:
        app.logger.info("Session %s", session)
        return "true"
    else:
        return "false"


@endpointV2.route('/v2/logout', methods=['GET'])
def logout():
    session['login_result'] = None
    return "logout"


@endpointV2.route('/v2/updateHistory/<username>', methods=['PUT'])
def update_history(username):
    content = request.get_json(silent=True)
    previous_chat = []
    # app.logger.info("Save Conversation :: %s",id)
    timeZ_Kl = pytz.timezone("Asia/kolkata")
    today = datetime.now(timeZ_Kl)
    save_chat = History.objects.get(username=username)
    previous_chat.extend(save_chat['conversation'])
    previous_chat.extend(content.get('conversation'))
    try:
        save_chat.conversation = previous_chat
        save_chat.save()
    except:
        print("Could not save")
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/clearVariable/<username>', methods=['DELETE'])
def delete_variables(username):
    SessionVariable.objects.filter(username=username).delete()
    return jsonify({'code': "200", 'message': "success"})

# @endpointV2.route('/v2/login', methods=['POST'])
# def login_user1():
#     URL = app.config["API_BASE_URL"]+"/login"
#     content = request.get_json(silent=True)
#     data = {"username": content.get("username") ,"password": content.get("password") }
#     result = requests.post(url = URL, data = data)
#     login_result = json.loads(result.text)
#     if login_result.get("access_token") == None:
#         print("wrong credentials")
#         return "wrong"
#     else:
#         session['login_result'] = login_result
#         session['user_name'] = content.get("username")
#         # session['access_token'] = {"token":login_result["access_token"]}
#         # session['refresh_token'] = {"token":login_result["refresh_token"]}
#         return "correct"

# @endpointV2.route('/v2/registerAccount', methods=['POST'])
# def register_account_user():
#     content = request.get_json(silent=True)
#     try:
#         account = AccountUser.objects.get(username = content.get("username"))
#     except Exception:
#         hased_password = generate_password_hash(content['password'],method='sha256')
#         account_user = AccountUser()
#         account_user.username = content.get("username")
#         account_user.password = hased_password
#         account_user.save()
#         create_follow_list(content.get("username"))
#         save_history(content.get("username"))
#         return jsonify({'code':"200",'message': "success"})

#     return jsonify({'code':"401",'message': "failed"})

# @endpointV2.route('/v2/login_user', methods=['POST'])
# def login_user():
#     content = request.get_json(silent=True)
#     app.logger.info("--> %s,%s",content.get("username"),content.get("password"))
#     try:
#         account_user = AccountUser.objects.get(username = content.get("username"))
#     except Exception:
#         app.logger.info("exception :: %s",Exception)
#         return jsonify({'code':"401",'error':'User not exist!'})
#     if not account_user:
#         return jsonify({'code':"401",'error':'User not exist!'})
#     else:
#         app.logger.info("account_user.expiryDate ==> %s",account_user.expiryDate)
#         if account_user.expiryDate != None:
#             dateTime1 = datetime.strptime(account_user.expiryDate, "%Y-%m-%d")
#             today = date.today()

#             dateTime2 = datetime.strptime(str(today), "%Y-%m-%d")
#             app.logger.info("data 1 --> %s,%s",dateTime1,dateTime2)
#         if account_user.expiryDate != None and dateTime2 > dateTime1:
#             return jsonify({'code':"402",'error':'User account expire'})

#         elif check_password_hash(account_user.password,content.get("password")):
#             session['user_name'] = content.get("username")
#             app.logger.info("Session in login ==> %s",session)
#             return jsonify({'code':"200",'message': "success"})

#     return jsonify({'code':"401",'error':'Entered password is wrong!'})


@endpointV2.route('/v2/getSessionVariables/<username>', methods=['GET'])
def get_session_variable(username):
    return Response(response=(
        SessionVariable.objects(
            username=username).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/checkupdates/<chatId>', methods=['GET'])
def get_backend_messages(chatId):
    resp = {}
    resp["chatId"] = chatId
    chat_message = ChatMessages.objects(chatId=chatId).first()
    if chat_message:
        resp["speechResponse"] = split_sentence(chat_message.message)
        ChatMessages.objects(chatId=chatId).delete()
        save_chat_messages(chatId, 'Bot', {}, resp)
    else:
        resp["speechResponse"] = []
    # save_chat_messages(chatId, 'Bot', {}, resp)
    return build_response.build_json(resp)


@endpointV2.route('/v2/deploymentStatus', methods=['GET'])
def get_deployment_status():
    data_list = {'data': {}, 'status': 'success', 'accounts': {}}
    userName = session['user_name']
    all_accounts = get_all_account()
    data_list['accounts'].update(all_accounts)
    registeredAccountsDoc = AccountSaved.objects.get(username=userName)
    registeredAcoounts = registeredAccountsDoc.account
    for d in registeredAcoounts:

        account_name_label = d.get('accountName')
        app.logger.info("Account Name --> %s", account_name_label)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer {}".format(session['login_result']['access_token'])
        }

        data = {
            "accountLabel": account_name_label
        }

        if d.get('accountType') == "AWS":
            URL = app.config["API_BASE_URL"]+"/api/" + \
                app.config['API_VERSION']+"/aws/ecs"
        elif d.get('accountType') == "AZURE":
            URL = app.config["API_BASE_URL"]+"/api/" + \
                app.config['API_VERSION']+"/azure/aci"

        data = json.dumps(data)
        result = requests.get(URL, headers=headers, data=data)
        deployment_result = json.loads(result.text)

        app.logger.info("deployment_result status code %s", result.status_code)

        if result.status_code == 200 and len(deployment_result['data']) > 0:
            app.logger.info("DEPLOYMENT_RESULT 1 --> %s", deployment_result)
            for item1 in deployment_result['data']:
                if(len(deployment_result['data'][item1]) > 0):
                    if d.get('accountType') == "AWS":
                        app.logger.info("DEPLOYMENT_RESULT 1 --> %s",
                                        deployment_result['data'][item1])
                        deployment_result['data'][item1][0].update(
                            {"account": account_name_label, 'type': "aws"})
                        app.logger.info("DEPLOYMENT_RESULT 2 --> %s",
                                        deployment_result['data'][item1])
                    elif d.get('accountType') == "AZURE":
                        app.logger.info("DEPLOYMENT_RESULT 1 --> %s",
                                        deployment_result['data'][item1])
                        deployment_result['data'][item1] = [{'PublicDnsName': deployment_result['data'][item1]['containerGroupFQDN'],
                                                             'ClusterName':deployment_result['data'][item1]['containerGroupName'], "account":account_name_label, 'type':"azure"}]
                        app.logger.info("DEPLOYMENT_RESULT 2 --> %s",
                                        deployment_result['data'][item1])

            data_list['data'].update(deployment_result['data'])
            app.logger.info("GET_DEPLOYMENT_STATUS 111--> %s", data_list)
        # time.sleep(5)
    return data_list


@endpointV2.route('/v2/updateProfileImage', methods=['POST'])
def profile_image():
    content = request.get_json(silent=True)
    try:
        exist = AccountSaved.objects.get(username=content.get("username"))
    except Exception:
        profile = AccountSaved()
        profile.username = content.get("username")
        profile.profileImage = "data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iaXNvLTg4NTktMSI/Pg0KPCEtLSBHZW5lcmF0b3I6IEFkb2JlIElsbHVzdHJhdG9yIDE5LjAuMCwgU1ZHIEV4cG9ydCBQbHVnLUluIC4gU1ZHIFZlcnNpb246IDYuMDAgQnVpbGQgMCkgIC0tPg0KPHN2ZyB2ZXJzaW9uPSIxLjEiIGlkPSJMYXllcl8xIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHhtbG5zOnhsaW5rPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5L3hsaW5rIiB4PSIwcHgiIHk9IjBweCINCgkgdmlld0JveD0iMCAwIDUwOCA1MDgiIHN0eWxlPSJlbmFibGUtYmFja2dyb3VuZDpuZXcgMCAwIDUwOCA1MDg7IiB4bWw6c3BhY2U9InByZXNlcnZlIj4NCjxjaXJjbGUgc3R5bGU9ImZpbGw6IzkwREZBQTsiIGN4PSIyNTQiIGN5PSIyNTQiIHI9IjI1NCIvPg0KPGc+DQoJPHBhdGggc3R5bGU9ImZpbGw6I0U2RTlFRTsiIGQ9Ik0yNTUuMiwzNjMuMmMtMC40LDAtMC44LDAuNC0xLjYsMC40Yy0wLjQsMC0wLjgtMC40LTEuNi0wLjRIMjU1LjJ6Ii8+DQoJPHBhdGggc3R5bGU9ImZpbGw6I0U2RTlFRTsiIGQ9Ik00NTguNCw0MDRjLTQ2LDYyLjgtMTIwLjgsMTA0LTIwNC44LDEwNFM5NS4yLDQ2Ny4yLDQ4LjgsNDA0YzM2LTM4LjQsODQuOC01OC44LDEyNS42LTY5LjINCgkJYy0zLjYsMjkuMiwxMS42LDY4LjQsMTIsNjcuMmMxNS4yLTM1LjIsNjYuOC0zOC40LDY2LjgtMzguNHM1MS42LDIuOCw2Ny4yLDM4LjRjMC40LDAuOCwxNS42LTM4LDEyLTY3LjINCgkJQzM3My42LDM0NS4yLDQyMi40LDM2NS42LDQ1OC40LDQwNHoiLz4NCjwvZz4NCjxwYXRoIHN0eWxlPSJmaWxsOiNGRkQwNUI7IiBkPSJNMzE2LjgsMzA4TDMxNi44LDMwOGMwLDUuMi0zLjIsMzIuOC02MS42LDU1LjJIMjUyYy01OC40LTIyLjQtNjEuNi01MC02MS42LTU1LjJsMCwwDQoJYzAuNC0xMC40LDIuOC0yMC44LDcuMi0zMC40YzE2LDE4LDM1LjIsMzAsNTYsMzBjMjAuNCwwLDQwLTExLjYsNTYtMzBDMzE0LDI4Ny4yLDMxNi44LDI5Ny42LDMxNi44LDMwOHoiLz4NCjxwYXRoIHN0eWxlPSJmaWxsOiNGMTU0M0Y7IiBkPSJNMjg4LjQsMzcyLjRMMjc1LjYsMzk4aC00NGwtMTIuOC0yNS42YzE3LjYtNy42LDM0LjgtOC44LDM0LjgtOC44UzI3MS4yLDM2NC44LDI4OC40LDM3Mi40eiIvPg0KPHBhdGggc3R5bGU9ImZpbGw6I0ZGNzA1ODsiIGQ9Ik0yMTgsNTA1LjZjMTEuNiwxLjYsMjMuNiwyLjQsMzYsMi40YzEyLDAsMjQtMC44LDM2LTIuNGwtMTQtMTA3LjJoLTQ0TDIxOCw1MDUuNnoiLz4NCjxnPg0KCTxwYXRoIHN0eWxlPSJmaWxsOiNGRkZGRkY7IiBkPSJNMzE2LjgsMzA3LjJjMCwwLDIuOCwzMi02My4yLDU2LjRjMCwwLDUxLjYsMi44LDY3LjIsMzguNEMzMjEuMiw0MDMuNiwzNTEuMiwzMjYsMzE2LjgsMzA3LjJ6Ii8+DQoJPHBhdGggc3R5bGU9ImZpbGw6I0ZGRkZGRjsiIGQ9Ik0xOTAuNCwzMDcuMmMtMzQsMTguOC00LjQsOTYtMy42LDk0LjhjMTUuMi0zNS4yLDY3LjItMzguNCw2Ny4yLTM4LjQNCgkJQzE4Ny42LDMzOS4yLDE5MC40LDMwNy4yLDE5MC40LDMwNy4yeiIvPg0KPC9nPg0KPHBhdGggc3R5bGU9ImZpbGw6I0Y5QjU0QzsiIGQ9Ik0zMTIuOCwyODUuNmMtMTYuOCwxOC0zNi44LDI5LjYtNTkuMiwyOS42cy00Mi40LTExLjYtNTkuMi0yOS42YzAuOC0yLjgsMi01LjYsMy4yLTgNCgljMTYsMTgsMzUuMiwzMCw1NiwzMHM0MC0xMS42LDU2LTMwQzMxMC44LDI4MCwzMTIsMjgyLjgsMzEyLjgsMjg1LjZ6Ii8+DQo8cGF0aCBzdHlsZT0iZmlsbDojRkZEMDVCOyIgZD0iTTM2Mi44LDIyNC40Yy04LjQsMTQtMjEuMiwyMi40LTMwLjgsMjAuOGMtMTkuMiwzNS42LTQ3LjIsNjItNzguNCw2MnMtNTkuMi0yNi44LTc4LjQtNjINCgljLTkuNiwxLjItMjIuNC02LjgtMzAuOC0yMC44Yy0xMC0xNi40LTEwLjQtMzQuNC0wLjgtNDAuNGMyLjQtMS4yLDQuOC0yLDcuNi0xLjZjNi40LDE2LjQsMTUuMiwyNi40LDE1LjIsMjYuNA0KCWMtOS4yLTUwLjgsMjguNC01Ni40LDIyLTEwNS4yYzAsMCwyMy42LDUyLjQsOTEuMiwxNS42bC01LjIsMTBjOTQuNC0yMS4yLDYyLjgsOTAsNjIsOTIuOGMxMC44LTEzLjYsMTcuNi0yNy4yLDIxLjYtMzkuNg0KCWMxLjYsMCwzLjYsMC44LDQuOCwxLjZDMzczLjIsMTg5LjYsMzcyLjgsMjA4LDM2Mi44LDIyNC40eiIvPg0KPHBhdGggc3R5bGU9ImZpbGw6IzMyNEE1RTsiIGQ9Ik0zMDgsNTAuOGM3LjYtMC44LDIwLDYsMjAsNmMtMzQtMzguOC04OS42LTE0LTg5LjYtMTRjMTguOC0xNiwzNS42LTE0LjQsMzUuNi0xNC40DQoJYy03OS42LTEyLTkzLjIsMzUuNi05My4yLDM1LjZjLTMuNi01LjYtMy42LTEzLjYtMy4yLTE3LjZDMTcyLDU2LDE3OCw3NS4yLDE3OCw3NS4yYy01LjYtMTQtMjUuMi0xMS42LTI1LjItMTEuNg0KCWMxNi44LDIuOCwxOS42LDEzLjIsMTkuNiwxMy4yYy00MiwxNS42LTM0LjgsNTkuMi0zNC44LDU5LjJsMTAtMTJjLTEyLjQsNDcuNiwxOS4yLDg0LjQsMTkuMiw4NC40Yy05LjItNTAuOCwyOC40LTU2LjQsMjItMTA1LjINCgljMCwwLDIzLjYsNTIuNCw5MS4yLDE1LjZsLTUuMiwxMGM5NS42LTIxLjYsNjIsOTMuMiw2Miw5My4yYzM0LTQzLjIsMjguOC04Ny42LDI4LjgtODcuNmw0LDE2QzM4MC40LDc4LjQsMzA4LDUwLjgsMzA4LDUwLjh6Ii8+DQo8Zz4NCjwvZz4NCjxnPg0KPC9nPg0KPGc+DQo8L2c+DQo8Zz4NCjwvZz4NCjxnPg0KPC9nPg0KPGc+DQo8L2c+DQo8Zz4NCjwvZz4NCjxnPg0KPC9nPg0KPGc+DQo8L2c+DQo8Zz4NCjwvZz4NCjxnPg0KPC9nPg0KPGc+DQo8L2c+DQo8Zz4NCjwvZz4NCjxnPg0KPC9nPg0KPGc+DQo8L2c+DQo8L3N2Zz4NCg=="
        profile.save()
        return "saved"
    if exist:
        return "saved"


@endpointV2.route('/v2/updateProfileImage/<username>', methods=['PUT'])
def update_image(username):
    content = request.get_json(silent=True)
    try:
        profile = AccountSaved.objects.get(username=username)
        profile.profileImage = content.get("profile_image")
        profile.save()
        return "update successfully"
    except Exception:
        return "error"


@endpointV2.route('/v2/getProfile/<username>', methods=['GET'])
def get_profile_image(username):
    return Response(response=(
        AccountSaved.objects(
            username=username).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/getAllAccount', methods=['GET'])
def get_all_account():
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer {}".format(session['login_result']['access_token'])
    }
    URL = app.config["API_BASE_URL"]+"/api/" + \
        app.config['API_VERSION']+"/cloud/accounts"

    result = requests.get(url=URL, headers=headers)
    all_account = json.loads(result.text)

    app.logger.info("ALL_ACCOUNT --> %s", result.status_code)
    if result.status_code == 401 and all_account['message'] == 'The token has expired.' and all_account['status'] == 'failed':
        refresh_token()
    return all_account


@endpointV2.route('/v2/updateFile/<id>', methods=['PUT'])
def update_file(id):
    content = request.get_json(silent=True)
    # try:
    profile = CatalogFile.objects.get(id=ObjectId(id))
    profile.fileDescription = content.get("file_description")
    profile.fileType = content.get("file_type")
    profile.createdBy = content.get("username")
    profile.project = content.get("project")
    profile.save()
    return jsonify({'code': "200", 'message': "success"})
    # except Exception:
    #     return "error"


@endpointV2.route('/v2/fileType', methods=['GET'])
def get_configFile():
    bot = Bot.objects.get(name="default")
    return build_response.build_json(bot.types)


@endpointV2.route('/v2/editFile/<fileName>/<userId>', methods=['GET'])
def edit_file(fileName, userId):
    data_file = os.path.join(
        app.config['UPLOAD_FOLDER']+"upload/"+userId+"/", fileName.lower())

    WORDS = []
    with open(data_file, "r") as file:
        for line in file.readlines():
            WORDS.append(line.rstrip())
    return jsonify({'code': "200", 'message': "success", "resp": json.dumps(WORDS)})


def getUsernameForPublic(filename):
    try:
        getUser = CatalogFile.objects.filter(Q(fileName=filename) & (
            Q(createdBy=session['user_name']) | Q(fileType="public")))
        app.logger.info("get user %s", getUser[0]['createdBy'])
        return getUser[0]['createdBy']
    except Exception:
        return session['user_name']


@endpointV2.route('/v2/catalogFileNameExist', methods=['GET'])
def catalog_file_exist():
    return Response(response=(
        CatalogFile.objects.filter(
            Q(createdBy=session['user_name'])).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/getModelConfig', methods=['GET'])
def get_model_file():
    config_list = ModelConfiguration.objects
    return build_response.sent_json(config_list.to_json())


@endpointV2.route('/v2/getAppConfig', methods=['GET'])
def get_apps_file():
    config_list = AppConfiguration.objects
    return build_response.sent_json(config_list.to_json())


@endpointV2.route('/v2/getServiceConfig', methods=['GET'])
def get_service_file():
    config_list = ServiceConfiguration.objects
    return build_response.sent_json(config_list.to_json())


@endpointV2.route('/v2/deleteInstance/<instanceName>/<accountName>', methods=['GET'])
def delete_instance(instanceName, accountName):
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer {}".format(session['login_result']['access_token'])
    }
    URL = app.config["API_BASE_URL"]+"/api/"+app.config['API_VERSION'] + \
        "/aws/ecs?accountLabel=%s&deploymentLabel=%s" % (
            accountName, instanceName)
    result = requests.delete(url=URL, headers=headers)
    delete_result = json.loads(result.text)
    if result.status_code == 200:
        return "Instance deleted successfully"
    else:
        return delete_result['data']


@endpointV2.route('/v2/downloadAttachment/<username>/<fileName>', methods=['GET'])
def download_Attachment(username, fileName):
    if fileName is None or fileName == 'undefined':
        return ""

    mimeType = mimetypes.MimeTypes().guess_type(fileName)[0]
    s3FileObj = S3Client.get_object("items/attachments/"+username+"/"+fileName)

    return Response(s3FileObj['Body'].read(), content_type=mimeType)


@endpointV2.route('/v2/downloadStatusAttachment/<id>/<fileName>', methods=['GET'])
def download_status_Attachment(id, fileName):
    if fileName is None or fileName == 'undefined':
        return ""

    mimeType = mimetypes.MimeTypes().guess_type(fileName)[0]
    s3FileObj = S3Client.get_object("status/attachments/"+id+"/"+fileName)

    return Response(s3FileObj['Body'].read(), content_type=mimeType)


@endpointV2.route('/v2/downloadItemAttachment/<username>/<fileName>', methods=['GET'])
def download_item_attachment(username, fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"attachments/"+username+"/", filename=fileName, as_attachment=True)


@endpointV2.route('/v2/downloadItemTempAttachment/<username>/<fileName>', methods=['GET'])
def download_item_temp_attachment(username, fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"temp/"+username+"/", filename=fileName, as_attachment=True)


@endpointV2.route('/v2/downloadFile/<username>/<fileName>', methods=['GET'])
def download_file(username, fileName):
    fileName = fileName.lower()
    if fileName is None or fileName == 'undefined':
        return ""

    mimeType = mimetypes.MimeTypes().guess_type(fileName)[0]
    s3FileObj = S3Client.get_object("upload/"+username+"/"+fileName)

    return Response(s3FileObj['Body'].read(), content_type=mimeType)
    # return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"upload/"+username+"/", filename=fileName.lower())


@endpointV2.route('/v2/downloadUserTempAttachment/<userId>/<fileName>', methods=['GET'])
def download_user_temp_attachment(userId, fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"temp/"+userId+"/", filename=fileName)


@endpointV2.route('/v2/setTimeZone', methods=['POST'])
def set_timezone():
    content = request.get_json(silent=True)
    session['time_zone'] = content.get('timezone')
    app.logger.info("set_timezone --> %s,%s", content.get('timezone'), session)
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getTotalCount', methods=['GET'])
def get_command_data_total():
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM projects.folio_cubes ")
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandData/<tableName>', methods=['GET'])
def get_command_data(tableName):
    tableName = tableName.lower()
    likeList = tableName.split()
    app.logger.info("likelist --> %s", likeList)
    searchWord = ""
    orToggle = False
    i = 1
    if "or" not in likeList and "and" not in likeList:
        for item in likeList:
            if len(likeList) > 1:
                searchWord += "table_name ILIKE '%"+item+"%' "
                if item != likeList[-1]:
                    searchWord += "and "
            else:
                searchWord += "table_name ILIKE '%"+item+"%' "
    else:
        previous_item = likeList[1]
        for item in range(0, len(likeList)):
            if item % 2:
                if previous_item != likeList[item]:
                    searchWord += ")"
                    orToggle = True
                searchWord += likeList[item]+" "
                previous_item = likeList[item]
            else:
                if orToggle or item == 0:
                    searchWord += "(table_name ILIKE '%"+likeList[item]+"%' "
                else:
                    searchWord += "table_name ILIKE '%"+likeList[item]+"%' "

        searchWord += ")"

    app.logger.info("searchWord --> %s", searchWord)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.folio_cubes WHERE " +
                searchWord+" ORDER BY table_name  limit 100 offset 0 ;")
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataForSearchBar/<tableName>', methods=['GET'])
def get_search_bar_result(tableName):
    tableName = tableName.lower()
    likeList = tableName.split()
    searchWord = ""
    if "or" not in likeList and "and" not in likeList:
        for item in likeList:
            if len(likeList) > 1:
                searchWord += item + ":* "
                if item != likeList[-1]:
                    searchWord += "& "
            else:
                searchWord += item + ":* "
    else:
        for item in likeList:
            if item == "or":
                searchWord += " | "
            elif item == "and":
                searchWord += " & "
            else:
                searchWord += item + ":* "
    app.logger.info("searchWord bar --> %s", searchWord)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.folio_cubes WHERE to_tsvector(table_name || ' ' || cube_type) @@ to_tsquery('" +
                searchWord+"') limit 20 offset 0 ;")
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDetail/<tableName>', methods=['GET'])
def get_command_detail(tableName):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    folio = getSchema(tableName)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    sortingClause = ""
    for item in columnList:
        if item.defaultSorting:
            sortingClause = " ORDER BY " + item.tableColumnName + " "
    cur.execute("SELECT * FROM "+folio+"."+tableName +
                sortingClause+" limit 100 offset 0 ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataCubes', methods=['GET'])
def get_command_data_cubes():
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM projects.folio_cubes ORDER BY table_name  limit 100 offset 0")
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataForComps/<folioNumber>/<index>', methods=['GET'])
def get_command_data_cubes_comps(folioNumber, index):
    finalResponse = []
    offsetValue = int(index) * 100
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from  projects.us_fl_miamidade_folio_cubes where folio = '" +
                folioNumber+"' ORDER BY folio limit 100 offset "+str(offsetValue))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataCompsEmail/<folioNumber>', methods=['GET'])
def get_command_data_cubes_comps_emails(folioNumber):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from  projects.us_fl_miamidade_folio_cubes where folio = '" +
                folioNumber+"' ORDER BY folio limit 50 offset 0")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataCubes/<index>', methods=['GET'])
def get_command_data_cubes1(index):
    offsetValue = int(index) * 100
    app.logger.info("offsetValue ==> %s,%s", offsetValue, index)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "SELECT * FROM projects.folio_cubes ORDER BY table_name  limit 100 offset "+str(offsetValue))
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDataCubesSearched/<index>/<searchWord>', methods=['GET'])
def get_command_data_cubes_search(index, searchWord):
    offsetValue = int(index) * 100
    app.logger.info("offsetValue ==> %s,%s", offsetValue, index)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.folio_cubes where (table_name ILIKE '%" +
                searchWord+"%') ORDER BY table_name limit 100 offset "+str(offsetValue))
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDetailCubes/<tableName>', methods=['GET'])
def get_command_detail_cubes(tableName):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    folio = getSchema(tableName)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    sortingClause = ""
    for item in columnList:
        if item.defaultSorting:
            sortingClause = " ORDER BY " + item.tableColumnName + " "
    cur.execute("SELECT * FROM "+folio+"."+tableName +
                sortingClause+" limit 100 offset 0 ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDetailCubes/<tableName>/<index>', methods=['GET'])
def get_command_detail_cubes1(tableName, index):
    finalResponse = []
    offsetValue = int(index) * 100
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    folio = getSchema(tableName)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    sortingClause = ""
    for item in columnList:
        if item.defaultSorting:
            sortingClause = " ORDER BY " + item.tableColumnName + " "
    cur.execute("SELECT * FROM "+folio+"."+tableName +
                sortingClause+" limit 100 offset "+str(offsetValue))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()

    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDetailCubesSearch/<tableName>/<index>/<word>', methods=['GET'])
def get_command_detail_cubes_search(tableName, index, word):
    finalResponse = []
    offsetValue = int(index) * 100
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    folio = getSchema(tableName)
    app.logger.info("folio ==> %s", folio)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    sortingClause = ""
    searchCond = " where "
    for item in columnList:
        if item.showColumn:
            searchCond += " ("+item.tableColumnName + \
                "::text ILIKE '%"+word+"%') or "

        if item.defaultSorting:
            sortingClause = " ORDER BY " + item.tableColumnName + " "

    cur.execute("SELECT * FROM "+folio+"."+tableName +
                searchCond[:-3]+sortingClause+"  limit 100 offset "+str(offsetValue))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCommandDetailCubesCompsSearch/<folioNumber>/<index>/<word>', methods=['GET'])
def get_command_data_cubes_comps_search(folioNumber, index, word):
    finalResponse = []
    offsetValue = int(index) * 100
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from  projects.us_fl_miamidade_folio_cubes where folio = '"+folioNumber+"' and (comp_folio ILIKE '%"+word+"%') or (comp_true_site_addr ILIKE '%"+word+"%') or (comp_true_site_city ILIKE '%" +
                word+"%')  or (comp_true_mailing_state ILIKE '%"+word+"%') or (comp_true_owner1 ILIKE '%"+word+"%') or (comp_true_site_zip_code ILIKE '%"+word+"%') ORDER BY folio limit 50 offset "+str(offsetValue))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMessageSearchList/<searchWord>', methods=['GET'])
def get_message_search_list(searchWord):
    config_list = MessageConfiguration.objects(
        Q(messageDate__contains=searchWord) | Q(fromMsg__contains=searchWord) | Q(messageType__contains=searchWord) | Q(reference__contains=searchWord) | Q(notes__contains=searchWord) | Q(cube__contains=searchWord))
    return build_response.sent_json(config_list.to_json())


@endpointV2.route('/v2/getThemeConfig', methods=['GET'])
def get_theme_config():
    config_list = ThemeConfig.objects.fields()
    return build_response.sent_json(config_list.to_json())


@endpointV2.route('/v2/getSchemaConfig/<name>', methods=['GET'])
def get_schema_config(name):
    folio = getSchema(name)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    app.logger.info("CONFIG LIST %s", config_list.id)
    return Response(response=(
        CubeColumnConfiguration.objects(schemaId=str(config_list.id)).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/getAboutUs', methods=['GET'])
def get_about_us():
    config_list = AboutUs.objects.fields()
    return build_response.sent_json(config_list.to_json())


def create_follow_list(username):
    follow = FollowerList()
    follow.username = username
    follow.save()
    comment = Comment()
    comment.username = username
    comment.save()
    return "success"

# def create_popular_list():
#     follow = PopularList()
#     follow.username = "default"
#     follow.save()
#     return "success"


@endpointV2.route('/v2/setFollows/<username>', methods=['PUT'])
def set_follow_list(username):
    content = request.get_json(silent=True)
    Flist = {}
    follow = FollowerList.objects.get(username=username)
    Flist.update(follow.table)
    Flist[content.get('tableName')] = [content.get('tableName'), content.get('updatedDate'), content.get('count'), content.get(
        'followDate'), content.get('folio'), content.get('cube_type'), content.get('value'), content.get('valueTotal')]
    follow.username = username
    follow.table = Flist
    follow.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setTag/<username>', methods=['PUT'])
def set_tag_list(username):
    content = request.get_json(silent=True)
    timeZ_Kl = pytz.timezone('Asia/Kolkata')
    today = datetime.now(timeZ_Kl)
    Flist = []
    tag = FollowerList.objects.get(username=username)
    Flist.extend(tag.tagged)
    Flist.extend([{"tableName": content.get('tableName'),
                   "taggedDate": today.strftime("%m/%d/%Y")}])
    tag.username = username
    tag.tagged = Flist
    tag.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setTagComment/<username>', methods=['PUT'])
def set_tag_comment(username):
    content = request.get_json(silent=True)
    timeZ_Kl = pytz.timezone('Asia/Kolkata')
    today = datetime.now(timeZ_Kl)
    Flist = {}
    tag = Comment.objects.get(username=username)
    Flist.update(tag.comments)
    if content.get('tableName') in Flist:
        Flist[content.get('tableName')].extend([{"comment": content.get(
            'comment'), "date": today.strftime("%m/%d/%Y"), "followUpDate": content.get("followUpDate")}])
    else:
        Flist[content.get('tableName')] = [{"comment": content.get('comment'), "date": today.strftime(
            "%m/%d/%Y"), "followUpDate": content.get("followUpDate")}]
    tag.username = username
    tag.comments = Flist
    tag.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setTagAttachment/<username>/<tableName>', methods=['PUT'])
def set_tag_attachment(username, tableName):
    Flist = {}
    if 'file' not in request.files:
        resp = jsonify({'message': 'No file part in the request'})
        resp.status_code = 400
        return resp

    scriptFile = request.files['file']
    Path(app.config['UPLOAD_FOLDER']+"attachments/" +
         username+"/").mkdir(parents=True, exist_ok=True)

    if scriptFile:
        scriptFile.save(os.path.join(
            app.config['UPLOAD_FOLDER']+"attachments/"+username+"/", scriptFile.filename.lower()))

    tag = Comment.objects.get(username=username)
    timeZ_Kl = pytz.timezone('Asia/Kolkata')
    today = datetime.now(timeZ_Kl)
    Flist.update(tag.attachments)
    if tableName in Flist:
        Flist[tableName].extend(
            [{"attach": scriptFile.filename, "date": today.strftime("%m/%d/%Y")}])
    else:
        Flist[tableName] = [
            {"attach": scriptFile.filename, "date": today.strftime("%m/%d/%Y")}]
    tag.username = username
    tag.attachments = Flist
    tag.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getComments/<username>/<tableName>', methods=['GET'])
def get_tag_comment(username, tableName):
    Flist = {}
    tag = Comment.objects.get(username=username)
    Flist.update(tag.comments)
    if tableName in Flist:
        return Response(response=dumps(Flist[tableName], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")
    else:
        return Response(response=dumps([], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAttachment/<username>/<tableName>', methods=['GET'])
def get_tag_attachments(username, tableName):
    Flist = {}
    tag = Comment.objects.get(username=username)
    Flist.update(tag.attachments)
    if tableName in Flist:
        return Response(response=dumps(Flist[tableName], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")
    else:
        return Response(response=dumps([], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTag/<username>', methods=['GET'])
def get_tag_list(username):
    tag = FollowerList.objects.get(username=username)
    finalTaggedList = []
    inString = ""
    blank = False
    for item in tag.tagged:
        inString += "'"+item['tableName']+"', "
        blank = True

    if blank:
        configuration = AdminConfiguration.objects().first()
        con = psycopg2.connect(database=configuration.database, user=configuration.user,
                               password=configuration.password, host=configuration.host, port=configuration.port)
        cur = con.cursor()
        cur.execute(
            "SELECT * FROM projects.folio_cubes WHERE table_name IN ("+inString[:-2]+")")
        rows = cur.fetchall()
        con.close()
        for item in rows:
            commentCount = 0
            attachmentCount = 0
            taggedDate = ""
            lastNote = ""
            app.logger.info("tag list item --> %s", item[0].strip())
            Flist = {}
            tag2 = Comment.objects.get(username=username)
            Flist.update(tag2.comments)
            if item[0].strip() in Flist:
                commentCount = len(Flist[item[0].strip()])
                lastNote = Flist[item[0].strip()][commentCount -
                                                  1]['followUpDate']
                app.logger.info(
                    "last note --> %s", Flist[item[0].strip()][commentCount-1]['followUpDate'])

            Flist1 = {}
            tag1 = Comment.objects.get(username=username)
            Flist1.update(tag1.attachments)
            if item[0].strip() in Flist1:
                attachmentCount = len(Flist1[item[0].strip()])
                app.logger.info("item comment --> %s",
                                len(Flist1[item[0].strip()]))

            tag = FollowerList.objects.get(username=username)
            for item1 in tag.tagged:
                taggedDate = item1['taggedDate']
            app.logger.info("item[0] --> %s", item[0])

            finalTaggedList.append({"cubesName": item[0].strip(), "commentCount": commentCount, "attachmentCount": attachmentCount, "taggedDate": taggedDate,
                                    "lastNote": lastNote, "update": item[3], "count": item[4], "cube_type": item[2].strip(), "folio": item[7], "value": item[5], "valueTotal": item[6]})

        return Response(response=dumps(finalTaggedList, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")
    else:
        return Response(response=dumps([], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTagDetails/<username>', methods=['GET'])
def get_tag_list_details(username):
    tag = FollowerList.objects.get(username=username)
    inString = ""
    finalTaggedList = []
    blank = False
    for item in tag.taggedDetails:
        folio = getSchema(item['tableName'])
        inString += " SELECT * FROM "+folio+"." + \
            item['tableName'] + " WHERE folio = '"+item['folio']+"' UNION"
        blank = True
    if blank:
        app.logger.info("getTagDetails ==> %s", inString.rsplit(' ', 1)[0])
        configuration = AdminConfiguration.objects().first()
        con = psycopg2.connect(database=configuration.database, user=configuration.user,
                               password=configuration.password, host=configuration.host, port=configuration.port)
        cur = con.cursor()
        cur.execute(inString.rsplit(' ', 1)[0])
        rows = cur.fetchall()
        con.close()
        for item in rows:
            commentCount = 0
            attachmentCount = 0
            taggedDate = ""
            lastNote = ""
            app.logger.info("tag list item --> %s", item[0].strip())
            Flist = {}
            tag2 = Comment.objects.get(username=username)
            Flist.update(tag2.comments)
            if item[0].strip() in Flist:
                commentCount = len(Flist[item[0].strip()])
                lastNote = Flist[item[0].strip()][commentCount -
                                                  1]['followUpDate']
                app.logger.info(
                    "last note --> %s", Flist[item[0].strip()][commentCount-1]['followUpDate'])

            Flist1 = {}
            tag1 = Comment.objects.get(username=username)
            Flist1.update(tag1.attachments)
            if item[0].strip() in Flist1:
                attachmentCount = len(Flist1[item[0].strip()])
                app.logger.info("item comment --> %s",
                                len(Flist1[item[0].strip()]))

            tag = FollowerList.objects.get(username=username)
            for item1 in tag.tagged:
                taggedDate = item1['taggedDate']

            finalTaggedList.append({"folio": item[0], "commentCount": commentCount, "attachmentCount": attachmentCount, "taggedDate": taggedDate, "lastNote": lastNote, "address": item[1],
                                    "city": item[2], "zipCode": item[3], "state": item[4], "owner": item[5], "bedroom": item[8], "price": item[11], "saleD": item[12], "map": item[13], "lat": item[15], "long": item[14]})
        return Response(response=dumps(finalTaggedList, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")
    else:
        return Response(response=dumps([], indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setTagDetails/<username>', methods=['PUT'])
def set_tag_details_list(username):
    content = request.get_json(silent=True)
    timeZ_Kl = pytz.timezone('Asia/Kolkata')
    today = datetime.now(timeZ_Kl)
    Flist = []
    tag = FollowerList.objects.get(username=username)
    Flist.extend(tag.taggedDetails)
    Flist.extend([{"folio": content.get('folio'), "tableName": content.get(
        'tableName'), "taggedDate": today.strftime("%m/%d/%Y")}])
    tag.username = username
    tag.taggedDetails = Flist
    tag.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getFollows/<username>', methods=['GET'])
def get_follow_list(username):
    return Response(response=(
        FollowerList.objects(username=username).to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/removeFollowerList/<username>', methods=['PUT'])
def remove_follow_list(username):
    content = request.get_json(silent=True)
    Flist = {}
    follow = FollowerList.objects.get(username=username)
    Flist.update(follow.table)
    Flist.pop(content.get('tableName'))
    follow.table = Flist
    follow.save()
    return jsonify({'code': "200", 'error': 'success'})


@endpointV2.route('/v2/removeTag/<username>', methods=['PUT'])
def remove_tag_list(username):
    content = request.get_json(silent=True)
    Flist = []
    tag = FollowerList.objects.get(username=username)
    Flist.extend(tag.tagged)
    Flist.remove(content.get('tableName'))
    tag.tagged = Flist
    tag.save()
    return jsonify({'code': "200", 'error': 'success'})


@endpointV2.route('/v2/removeTagDetail/<username>', methods=['PUT'])
def remove_tag_detail(username):
    content = request.get_json(silent=True)
    Flist = []
    tag = FollowerList.objects.get(username=username)
    Flist.extend(tag.taggedDetails)
    # Flist.remove(content.get('tableName'))
    for i in range(len(Flist)):
        if Flist[i]['folio'] == content.get('folio'):
            del Flist[i]
            break
    tag.taggedDetails = Flist
    tag.save()
    return jsonify({'code': "200", 'error': 'success'})


@endpointV2.route('/v2/setRecentList/<username>', methods=['PUT'])
def set_recent_list(username):
    content = request.get_json(silent=True)
    Flist = {}
    follow = FollowerList.objects.get(username=username)
    Flist.update(follow.recent)
    Flist[content.get('tableName')] = [content.get('tableName'), content.get('updatedDate'), content.get('count'), content.get(
        'followDate'), content.get('folio'), content.get('cube_type'), content.get('value'), content.get('valueTotal')]
    follow.username = username
    follow.recent = Flist
    follow.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setPopularList', methods=['PUT'])
def set_popular_list():
    content = request.get_json(silent=True)
    Flist = {}
    popularL = PopularList.objects.get(username="default")
    Flist.update(popularL.popular)
    Flist[content.get('tableName')] = [content.get('tableName'), content.get('updatedDate'), content.get('count'), content.get(
        'followDate'), content.get('folio'), content.get('cube_type'), content.get('value'), content.get('valueTotal')]
    popularL.username = "default"
    popularL.popular = Flist
    popularL.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getPopularList', methods=['GET'])
def get_popular_list():
    return Response(response=(
        PopularList.objects(username="default").to_json()),
        status=200,
        mimetype="application/json")


@endpointV2.route('/v2/setTrendingList', methods=['PUT'])
def set_trending_list():
    content = request.get_json(silent=True)
    Flist = {}
    trendingL = PopularList.objects.get(username="default")
    Flist.update(trendingL.trending)
    if content.get('tableName') in Flist:
        previous_count = Flist[content.get('tableName')][3]
        Flist[content.get('tableName')] = [content.get('tableName'), content.get('updatedDate'), content.get('count'), previous_count+1,
                                           content.get('followDate'), content.get('folio'), content.get('cube_type'), content.get('value'), content.get('valueTotal')]
    else:
        Flist[content.get('tableName')] = [content.get('tableName'), content.get('updatedDate'), content.get('count'), content.get(
            'trendingCount'), content.get('followDate'), content.get('folio'), content.get('cube_type'), content.get('value'), content.get('valueTotal')]
    trendingL.trending = Flist
    trendingL.save()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/sendEmail/<email>', methods=['POST'])
def set_email(email):
    bodyData = []
    columnValue = []
    content = request.get_json()
    filename = content.get('subject')+".xlsx"
    schema = getSchema(content.get('subject'))
    config_list = CubeSchemaConfiguration.objects.get(schemaName=schema)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    for item in columnList:
        if item.showColumn:
            columnValue.append(item.tableColumnName)
    link = get_copy_link_for_email(content.get(
        'subject'), content.get('body'), content.get('location'))
    if(content.get('emailData') == "attachment"):
        wb = Workbook()
        sheet1 = wb.add_sheet('Sheet 1')
        index = 0
        for item in columnList:
            if item.showColumn:
                sheet1.write(0, index, item.columnDisplayName)
                index = index+1

        for i, row in enumerate(content.get('body')):
            firstIndex = i+1
            for item in row:
                for index, item1 in enumerate(columnValue):
                    sheet1.write(firstIndex, index, item[item1])

        wb.save(os.path.join(
            app.config['UPLOAD_FOLDER']+"attachments/", filename))
    else:
        bodyData = content.get('body1').split('\n')
        html1 = ""
        for i in bodyData:
            html1 += "<p>"+i+"<p><br\>"
        html1 += link+"<br\>"
        css = 'style="padding:5px; font-family: Arial,sans-serif; font-size: 16px; line-height:20px;line-height:30px;"'

        html = '<table width="100%" cellpadding="0" cellspacing="0" style="min-width:100%;border:1px solid #333;"><thead><tr>'
        for item in columnList:
            if item.showColumn:
                html += '<th scope="col" '+css+'>'+item.columnDisplayName+'</th>'
        html += '</tr></thead><tbody>'
        # html += '<thead><tr><th scope="col" '+css+'>Folio</th><th scope="col" '+css+'>Address</th><th scope="col" '+css+'>City</th><th scope="col" '+css+'>Zip Code</th><th scope="col" '+css+'>State</th><th scope="col" '+css+'>Bedrooms</th><th scope="col" '+css+'>Sales Date</th></tr></thead><tbody>'
        for i, row in enumerate(content.get('body')):
            html += "<tr>"
            for index, item in enumerate(row):
                for item1 in columnValue:
                    html += "<td valign='top' style='padding:5px; font-family: Arial,sans-serif; font-size: 16px; line-height:20px;border:1px solid #333;'>" + \
                        item[item1] + "</td>"
            html += "</tr>"
        html += "</tbody></table>"

    msg = Message(
        content.get('subject'),
        sender=('Istoria Team', mailSender),
        recipients=[email]
    )
    filepath = r''+app.config['UPLOAD_FOLDER']+"attachments"+"/"+filename

    if(content.get('emailData') == "attachment"):
        msg.body = content.get('body1')+"\n"+link
        with app.open_resource(filepath) as fp:
            msg.attach(filename, "application/octect-stream", fp.read())
    else:
        msg.html = html1 + " " + html

    mail.send(msg)
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCubesDetailEmail/<tableName>', methods=['GET'])
def get_command_detail_email(tableName):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    folio = getSchema(tableName)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=folio)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    sortingClause = ""
    for item in columnList:
        if item.defaultSorting:
            sortingClause = " ORDER BY " + item.tableColumnName + " "
    cur.execute("SELECT * FROM "+folio+"."+tableName +
                sortingClause+"  limit 50 offset 0")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCopyLink/<name>', methods=['POST'])
def get_copy_link(name):
    columnValue = []
    content = request.get_json(silent=True)
    config_list = ThemeConfig.objects.get()
    logo_url = config_list.logo
    favicon = config_list.favicon
    filename = name+".xlsx"
    schema = getSchema(name)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=schema)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    columnHtml = """ """
    for item in columnList:
        if item.showColumn:
            columnHtml += """<th>"""+item.columnDisplayName+"""</th>"""
            columnValue.append(item.tableColumnName)
    html = """ """
    mapH = """["""
    for i, row in enumerate(content.get('data')):
        html += """<tr>"""
        for index, item in enumerate(row):
            for item1 in columnValue:
                html += """<td>""" + item[item1] + """</td>"""
        html += """</tr>"""

    # app.logger.info("lat long ==> %s",html)
    for item in content.get('location'):
        mapH += """['"""+item['shelter']+"""',"""+str(item['latitude'])+""","""+str(
            item['longitude'])+""",'"""+str(item['location']) + """'],"""
    mapH += """]"""

    html_str = """<head>
    <meta http-equiv="pragma" content="no-cache" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    <link rel="shortcut icon" id="favicon" type="image/png" href=" """ + favicon+""" " />
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.21/css/jquery.dataTables.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/1.6.2/css/buttons.dataTables.min.css">
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
</head><div style="text-align:center;"><img src=" """+logo_url+""" " style="width:150px"></img><br>
    <h2>"""+name + """</h2></div><br>
    <table id="table_id" class="display">
    <thead>
        <tr>
        """ + columnHtml + """
        </tr>
        <thead>
        <tbody>""" + html + """<tbody></table>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.10.21/js/jquery.dataTables.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/dataTables.buttons.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.flash.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/pdfmake.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/vfs_fonts.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.3/jszip.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.html5.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.print.min.js"></script>
        <script type="text/javascript">$(document).ready( function () {
    $('#table_id').DataTable({
        dom: 'Bfrtip',
        buttons: [
            {
                extend: 'excel',
                title: ' """+name+"""'
            },
            {
                extend: 'pdf',
                title: '"""+name+"""',
                orientation : 'landscape',
                pageSize : 'LEGAL',
            },
            {
                text: 'Map',
                action: function ( e, dt, button, config ) {
                window.open('"""+Production.host + """/cubes/map/"""+name+"""',"_blank") ;
                    } 
            }
        ]
    });
} );</script>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "copiedFile/html/").mkdir(parents=True, exist_ok=True)
    # Path(app.config['UPLOAD_FOLDER']+"copiedFile/xlsx/").mkdir(parents=True, exist_ok=True)

    filepath = r''+app.config['UPLOAD_FOLDER']+"copiedFile/html/"+name+".html"
    with open(filepath, "w") as file:
        file.write(html_str)

    mapHtml = """<head> 
                    <meta http-equiv="content-type" content="text/html; charset=UTF-8" /> 
                    <title>Google Maps Multiple Markers</title> 
                    <script src="//maps.google.com/maps/api/js?sensor=false" 
                            type="text/javascript"></script>
                    </head> 
                    <body>
                    <div id="map" style="width: 100%; height: 100%;"></div>

                    <script type="text/javascript">
                        var locations = """+mapH+""";

                        var map = new google.maps.Map(document.getElementById('map'), {
                        zoom: 13,
                        center: new google.maps.LatLng("""+str(content.get('location')[0]['latitude'])+""", """+str(content.get('location')[0]['longitude'])+"""),
                        mapTypeId: google.maps.MapTypeId.ROADMAP
                        });

                        var infowindow = new google.maps.InfoWindow();

                        var marker, i;

                        for (i = 0; i < locations.length; i++) {  
                        marker = new google.maps.Marker({
                            position: new google.maps.LatLng(locations[i][1], locations[i][2]),
                            map: map
                        });

                        google.maps.event.addListener(marker, 'click', (function(marker, i) {
                            return function() {
                            infowindow.setContent(locations[i][0]+' <br><a href="'+locations[i][3]+'" target="_blank">Location</a>');
                            infowindow.open(map, marker);
                            }
                        })(marker, i));
                        }
                    </script>
                    </body>"""
    Path(app.config['UPLOAD_FOLDER'] +
         "copiedFile/map/").mkdir(parents=True, exist_ok=True)
    filepath = r''+app.config['UPLOAD_FOLDER']+"copiedFile/map/"+name+".html"
    with open(filepath, "w") as file:
        file.write(mapHtml)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/downloadCopyFile/<fileName>', methods=['GET'])
def download_copy_file(fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"copiedFile/", filename=fileName)


@endpointV2.route('/v2/getCommandIntent/<searchWord>', methods=['GET'])
def get_command_search_data(searchWord):
    intent_id, confidence, suggestions = predict(searchWord)
    intent = Intent.objects.get(intentId=intent_id)
    extracted_parameters = entity_extraction.predictMultiAttr(
        intent_id, searchWord)
    app.logger.info("extracted_parameters: %s",
                    extracted_parameters['search_text'])
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.folio_cubes where (table_name ILIKE '%" +
                extracted_parameters['search_text']+"%') ORDER BY table_name limit 50 offset 0")
    rows = cur.fetchall()
    con.close()
    return Response(response=dumps(rows, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


def getSchema(tableName):
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "SELECT schema_name FROM projects.folio_cubes WHERE table_name = '"+tableName.strip()+"'")
    rows = cur.fetchall()
    con.close()
    return rows[0][0].strip()


def get_copy_link_for_email(name, Data, Location):
    columnValue = []
    # content = request.get_json(silent=True)
    config_list = ThemeConfig.objects.get()
    logo_url = config_list.logo
    favicon = config_list.favicon
    filename = name+".xlsx"
    schema = getSchema(name)
    config_list = CubeSchemaConfiguration.objects.get(schemaName=schema)
    columnList = CubeColumnConfiguration.objects(schemaId=str(config_list.id))
    columnHtml = """ """
    for item in columnList:
        if item.showColumn:
            columnHtml += """<th>"""+item.columnDisplayName+"""</th>"""
            columnValue.append(item.tableColumnName)
    html = """ """
    mapH = """["""
    for i, row in enumerate(Data):
        html += """<tr>"""
        for index, item in enumerate(row):
            for item1 in columnValue:
                html += """<td>""" + item[item1] + """</td>"""
        html += """</tr>"""

    # app.logger.info("lat long ==> %s",html)
    for item in Location:
        mapH += """['"""+item['shelter']+"""',"""+str(item['latitude'])+""","""+str(
            item['longitude'])+""",'"""+str(item['location']) + """'],"""
    mapH += """]"""

    html_str = """<head>
    <meta http-equiv="pragma" content="no-cache" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    <link rel="shortcut icon" id="favicon" type="image/png" href=" """ + favicon+""" " />
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.21/css/jquery.dataTables.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/1.6.2/css/buttons.dataTables.min.css">
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
</head><div style="text-align:center;"><img src=" """+logo_url+""" " style="width:150px"></img><br>
    <h2 style="text-align:center;">"""+name + """</h2></div><br>
    <table id="table_id" class="display">
    <thead>
        <tr>
        """ + columnHtml + """
        </tr>
        <thead>
        <tbody>""" + html + """<tbody></table>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.10.21/js/jquery.dataTables.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/dataTables.buttons.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.flash.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/pdfmake.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/vfs_fonts.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.3/jszip.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.html5.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.print.min.js"></script>
        <script type="text/javascript">$(document).ready( function () {
    $('#table_id').DataTable({
        dom: 'Bfrtip',
        buttons: [
            {
                extend: 'excel',
                title: ' """+name+"""'
            },
            {
                extend: 'pdf',
                title: '"""+name+"""',
                orientation : 'landscape',
                pageSize : 'LEGAL',
            },
            {
                text: 'Map',
                action: function ( e, dt, button, config ) {
                window.open('"""+Production.host + """/cubes/map/"""+name+"""',"_blank") ;
                    } 
            }
        ]
    });
} );</script>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "copiedFile/html/").mkdir(parents=True, exist_ok=True)
    # Path(app.config['UPLOAD_FOLDER']+"copiedFile/xlsx/").mkdir(parents=True, exist_ok=True)

    filepath = r''+app.config['UPLOAD_FOLDER']+"copiedFile/html/"+name+".html"
    with open(filepath, "w") as file:
        file.write(html_str)

    mapHtml = """<head> 
                    <meta http-equiv="content-type" content="text/html; charset=UTF-8" /> 
                    <title>Google Maps Multiple Markers</title> 
                    <script src="//maps.google.com/maps/api/js?sensor=false" 
                            type="text/javascript"></script>
                    </head> 
                    <body>
                    <div id="map" style="width: 100%; height: 100%;"></div>

                    <script type="text/javascript">
                        var locations = """+mapH+""";

                        var map = new google.maps.Map(document.getElementById('map'), {
                        zoom: 13,
                        center: new google.maps.LatLng("""+str(Location[0]['latitude'])+""", """+str(Location[0]['longitude'])+"""),
                        mapTypeId: google.maps.MapTypeId.ROADMAP
                        });

                        var infowindow = new google.maps.InfoWindow();

                        var marker, i;

                        for (i = 0; i < locations.length; i++) {  
                        marker = new google.maps.Marker({
                            position: new google.maps.LatLng(locations[i][1], locations[i][2]),
                            map: map
                        });

                        google.maps.event.addListener(marker, 'click', (function(marker, i) {
                            return function() {
                            infowindow.setContent(locations[i][0]+' <br><a href="'+locations[i][3]+'" target="_blank">Location</a>');
                            infowindow.open(map, marker);
                            }
                        })(marker, i));
                        }
                    </script>
                    </body>"""
    Path(app.config['UPLOAD_FOLDER'] +
         "copiedFile/map/").mkdir(parents=True, exist_ok=True)
    filepath = r''+app.config['UPLOAD_FOLDER']+"copiedFile/map/"+name+".html"
    with open(filepath, "w") as file:
        file.write(mapHtml)

    return Production.host+"/cubes/"+name+".html"

# @endpointV2.route('/v2/getexcelDownload/<name>', methods=['POST'])
# def downloadExcel(name):


@endpointV2.route('/v2/getAllItems/<id>', methods=['GET'])
def get_items(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id ="+str(id)
        else:
            query = ""

    cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.team_members u on u.id = tagtype), (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , pu1.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id  left join projects.users pu1 on projects.items.user_id = pu1.id  left join projects.collections on projects.items.collection = projects.collections.id  "+query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMyItems/<id>', methods=['GET'])
def get_my_items(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    teamAssignee = None
    assigneeQ = ""
    cur.execute(
        "select team_member_id from projects.team_member_mapping where user_id ='"+id+"' limit 1")
    row1 = cur.fetchall()
    if len(row1) > 0:
        teamAssignee = row1[0][0]
        assigneeQ = " and "+str(teamAssignee) + \
            " = Any(projects.items.assignee) "

        cur.execute(
            'select invite_by,project from projects.user_project_mapping where user_id ='+id)
        rows = cur.fetchall()
        if len(rows) > 0:
            inviteUserId = rows[0][0]
            projectArr = rows[0][1]
            query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
                inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+") and projects.items.assignee IS NOT NULL "+assigneeQ
        else:
            cur.execute(
                'select type, username from projects.users where id ='+id)
            rows = cur.fetchall()
            userType = rows[0][0]
            username = rows[0][1]
            cur.execute(
                "select project from projects.invite where email ='"+username+"'")
            rows = cur.fetchall()
            pInvite = False
            if len(rows) > 0:
                projectUserList = rows[0][0]
                pInvite = True
            if userType == "I" and pInvite == True:
                query = "WHERE projects.items.user_id ="+str(id)+" or projects.items.project = ANY(Array"+str(
                    projectUserList)+") and projects.items.assignee IS NOT NULL "+assigneeQ
            elif userType == "I" and pInvite == False:
                query = "WHERE projects.items.user_id =" + \
                    str(id)+" and projects.items.assignee IS NOT NULL" + assigneeQ
            else:
                query = " where projects.items.assignee IS NOT NULL" + assigneeQ

        cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.team_members u on u.id = tagtype), (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , pu1.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id  left join projects.users pu1 on projects.items.user_id = pu1.id  left join projects.collections on projects.items.collection = projects.collections.id  "+query)
        colnames = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        result = []
        for item1 in rows:
            columnValue = {}
            for index, item in enumerate(item1):
                columnValue[colnames[index]] = item
            finalResponse.append(columnValue)
        con.close()

    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllItemsLimit/<id>', methods=['GET'])
def get_items_limit(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id ="+str(id)
        else:
            query = ""

    cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.users u on u.id = tagtype), (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , pu1.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id  left join projects.users pu1 on projects.items.user_id = pu1.id  left join projects.collections on projects.items.collection = projects.collections.id  "+query+" order by projects.items.id desc limit 40")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionOpenItems/<userId>/<id>/<itemType>', methods=['GET'])
def get_items_collection_open_items(userId, id, itemType):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+userId)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = " and projects.items.user_id="+str(userId)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        query = ""

    if itemType == "open":
        itemT = "and projects.items.status = 1 "
    elif itemType == "progress":
        itemT = " and projects.items.status != 6 and projects.items.status != 1 "
    elif itemType == "closed":
        itemT = "and projects.items.status = 6 "
    elif itemType == "qa":
        itemT = "and projects.items.status = 7 "
    elif itemType == "estimate":
        itemT = "and projects.items.estimate != '0' and projects.items.estimate is not null "
    elif itemType == "actual":
        itemT = "and projects.items.actual != '0' and projects.items.actual is not null "
    elif itemType == "over_estimate":
        itemT = "and NULLIF(estimate, '')::numeric > NULLIF(actual, '')::numeric "
    else:
        itemT = "and projects.items.status = 5 "

    cur.execute("select projects.items.*, (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), projects.collections.collection as collection_name , projects.users.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id  where projects.items.collection ="+str(id)+itemT + query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllItemsFilter/<id>/<filterType>/<filterId>', methods=['GET'])
def get_items_filter(id, filterType, filterId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = " where  projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+") and "
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True

        if userType == "I" and pInvite == True:
            query = " where projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") and "
        elif userType == "I" and pInvite == False:
            query = " where projects.items.user_id ="+str(id)+" and "
        else:
            query = " where "
    if (filterType != "tagtype"):
        cur.execute("select projects.items.*, (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id " + query + "projects.items."+filterType+" = "+filterId)
    else:
        cur.execute("select projects.items.*, (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where "+query + filterId+" = Any(projects.items."+filterType+")")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectFilter/<id>/<ptype>/<projectId>', methods=['GET'])
def get_project_filter(id, ptype, projectId):
    filter_type = ""
    if ptype == "1":
        filter_type = " projects.items.status != 6"
    elif ptype == "2":
        filter_type = " projects.items.priority = 2"
    elif ptype == "3":
        filter_type = " projects.items.priority = 3"
    elif ptype == "4":
        filter_type = " projects.items.priority = 4"
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "and projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+") "
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows):
            projectUserList = rows[0][0]
            pInvite = True

        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") "
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id ="+str(id)
        else:
            query = ""
        # query = ""
    cur.execute("select projects.items.*, (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), projects.collections.collection as collection_name , projects.users.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where " + filter_type+" and projects.items.project="+projectId + query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setItem/<userId>', methods=['POST'])
def set_items(userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if (content.get("tagType") is not None and len(content.get("tagType")) > 0):
        cur.execute('INSERT INTO projects.items (USER_ID,PROJECT, DATE, DESCRIPTION, PRIORITY, ESTIMATE,ASSIGNEE, STATUS,TYPE,CREATED_ON,COLLECTION,ACTUAL,tagType) VALUES (%s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s,%s,%s) RETURNING id', (userId, content.get("project"), content.get(
            "date"), content.get("description"), content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), content.get('dateTime'), content.get("collection"), content.get("actual"), content.get("tagType")))
    else:
        cur.execute('INSERT INTO projects.items (USER_ID,PROJECT, DATE, DESCRIPTION, PRIORITY, ESTIMATE,ASSIGNEE, STATUS,TYPE,CREATED_ON,COLLECTION,ACTUAL) VALUES (%s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s,%s) RETURNING id', (userId, content.get(
            "project"), content.get("date"), content.get("description"), content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), content.get('dateTime'), content.get("collection"), content.get("actual")))
    ()
    rows = cur.fetchall()
    id = rows[0][0]
    cur.execute('Insert into projects.ITEMS_Comment_status  (items_id, status, date, user_id) values(%s,%s,%s,%s)',
                (id, content.get("status"), content.get("date"), userId))
    if content.get("status") == 6:
        cur.execute('UPDATE projects.projects SET last_closed_date = %s WHERE id = %s',
                    (now, content.get("project")))
    cur.execute('select item_count,prefix from projects.projects where id =' +
                str(content.get("project")))
    rows = cur.fetchall()
    count = rows[0][0]
    prefix = rows[0][1]
    item_id = prefix + "-" + str(count+1)
    cur.execute(
        'UPDATE projects.items SET ITEM_ID = %s WHERE id = %s', (item_id, id))
    cur.execute('UPDATE projects.projects SET item_count = %s WHERE id = %s',
                (count+1, content.get("project")))
    cur.execute('UPDATE projects.collections SET last_activity= %s WHERE id = %s',
                (now.strftime("%m-%d-%Y %I:%M %p"), content.get('collection')))
    con.commit()
    con.close()

    try:
        idsList = [id]
        if ES_SYNC_ON:
            indexItems(idsList)
    except Exception as ex:
        pass

    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/setItemMulti/<userId>', methods=['POST'])
def set_items_multi(userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = None
    ids = []
    attachmentIds = []
    descriptionList = content.get("description")
    assign_count = 0
    if content.get('collection') != None:
        assign_count = 1
    for description in descriptionList:
        followupDate = content.get("followup")
        if followupDate is None or followupDate == '':
            followupDate = None

        if (len(content.get("tagType")) > 0):
            rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items (USER_ID,PROJECT, DATE, DESCRIPTION, PRIORITY, ESTIMATE,ASSIGNEE, STATUS,TYPE,CREATED_ON,COLLECTION,ACTUAL,tagType, title, topic, followup, update_count, assign_count, due_date, epic, ide, blocked) VALUES (%s, %s, NULLIF(%s, \'\')::date, %s, %s, %s, %s,%s,%s,%s,%s, = NULLIF(%s, \'\')::date, %s,%s, NULLIF(%s, \'\')::date, %s,%s,%s) RETURNING id', (userId,
                                                                                                                                                                                                                                                                                                                                                                                                                                                   content.get("project"), content.get("date"), description, content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), now, content.get("collection"), content.get("actual"), content.get("tagType"), content.get("title"), content.get("topic"), followupDate, "0", assign_count, content.get("due_date"), content.get("epic"), content.get("ide"), content.get('blocked')))
        else:
            rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items (USER_ID,PROJECT, DATE, DESCRIPTION, PRIORITY, ESTIMATE,ASSIGNEE, STATUS,TYPE,CREATED_ON,COLLECTION,ACTUAL, title, topic, followup, update_count, assign_count, due_date, epic, ide, blocked) VALUES (%s, %s, NULLIF(%s, \'\')::date, %s, %s, %s, %s,%s,%s,%s,%s,%s,%s,%s, NULLIF(%s, \'\')::date,%s, %s, NULLIF(%s, \'\')::date,%s,%s,%s) RETURNING id',
                                                          (userId, content.get("project"), content.get("date"), description, content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), now, content.get("collection"), content.get("actual"), content.get("title"), content.get("topic"), followupDate, "0", assign_count, content.get("due_date"), content.get("epic"), content.get("ide"), content.get('blocked')))

        id = rows[0][0]
        ids.append(id)
        SQLHelpers.getInstance().executeUpdate('Insert into projects.ITEMS_Comment_status  (items_id, status, date, user_id) values(%s,%s,%s,%s)',
                                               (id, content.get("status"), content.get("date"), userId))

        if content.get("status") == 6:
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.items SET date_close = %s WHERE id = %s', (now, id))
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.projects SET last_closed_date = %s WHERE id = %s', (now, content.get("project")))
        elif content.get("status") == 3:
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.items SET inprogress_date = %s WHERE id = %s', (now, id))
        elif content.get("status") == 5:
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.items SET completed_date = %s WHERE id = %s', (now, id))

        rows = SQLHelpers.getInstance().executeRawResult(
            'select item_count,prefix from projects.projects where id ='+str(content.get("project")))
        count = rows[0][0]
        prefix = rows[0][1]
        item_id = prefix + "-" + str(count+1)
        SQLHelpers.getInstance().executeUpdate(
            'UPDATE projects.items SET ITEM_ID = %s WHERE id = %s', (item_id, id))
        SQLHelpers.getInstance().executeUpdate(
            'UPDATE projects.projects SET item_count = %s WHERE id = %s', (count+1, content.get("project")))
        SQLHelpers.getInstance().executeUpdate('UPDATE projects.collections SET last_activity= %s WHERE id = %s',
                                               (now.strftime("%m-%d-%Y %I:%M %p"), content.get('collection')))

        if content.get('blocked'):
            ref_id = item_id
            li = []
            li.append(int(content.get("project")))
            SQLHelpers.getInstance().executeUpdate('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information, activity_id, reference_id, reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                                   (li, userId, ref_id+" marked as Blocked", ref_id, now, now.strftime("%I:%M %p"), description, '9', id, 'I', 'Item Updated'))

        if (content.get("tempAttachment") is not None and len(content.get("tempAttachment")) > 0):
            for fileAttach in content.get("tempAttachment"):
                try:
                    Path(app.config['UPLOAD_FOLDER']+"attachments/" +
                         str(id)+"/").mkdir(parents=True, exist_ok=True)
                    shutil.move(app.config['UPLOAD_FOLDER']+"temp/"+userId+"/"+fileAttach,
                                app.config['UPLOAD_FOLDER']+"attachments/"+str(id)+"/"+fileAttach)

                    S3Client.upload_file(os.path.join(app.config['UPLOAD_FOLDER']+"attachments/"+str(
                        id)+"/", fileAttach), "items/attachments/"+str(id)+"/"+fileAttach)

                    attRows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items_attachment (ITEMS_ID,COMMENT,ATTACHMENT, DATE, USER_BY) VALUES (%s, %s, %s,%s, %s) RETURNING id',
                                                                     (str(id), 'Uploaded Attachment', fileAttach, now.strftime("%m-%d-%Y %I:%M %p"), content.get("userId")))
                    attachmentIds.append(attRows[0][0])
                except Exception as ex:
                    app.logger.info(
                        "Error in moving temporary attachments: %s", traceback.format_exc())

        rows = SQLHelpers.getInstance().executeRawResult(
            'select item_id from projects.items where id ='+str(id))
        ref = rows[0][0]
        ref_type = "I"
        ref_id = id

        li = []
        li.append(int(content.get("project")))
        activity = ""
        collection = content.get("collection")
        app.logger.info("Collection : %s", collection)
        if(collection is not None and str(collection) != ""):
            rows2 = SQLHelpers.getInstance().executeRawResult(
                'select id, collection from projects.collections where id ='+str(collection))
            activity = "Collection : "+rows2[0][1]
        if (len(content.get("tagType")) > 0):
            SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.item_tag (ITEM_ID, USER_ID, DATE) VALUES (%s,%s, %s)',
                                                   (id, userId, datetime.today().strftime('%Y-%m-%d')))

        SQLHelpers.getInstance().executeUpdate('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information, activity_id, reference_id,reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                               (li, userId, activity, ref, now, now.strftime("%I:%M %p"), description, 1, ref_id, ref_type, 'Item added'))

    try:
        if ES_SYNC_ON:
            indexItems(ids)
            indexItemAttachmentDocs(attachmentIds)
    except Exception as ex:
        pass

    return jsonify({'code': "200", 'message': "success", "id": ids})


@endpointV2.route('/v2/setItemTags/<itemId>/<userId>', methods=['POST'])
def set_items_tags(itemId, userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    if (content.get("tagType") is not None):
        app.logger.info("Update Tag Type:: %s", content.get("tagType"))
        SQLHelpers.getInstance().executeUpdate(
            "UPDATE projects.items set tagType=%s where id=%s", (content.get("tagType"), itemId))
    if (content.get("tagType") is None or len(content.get("tagType")) <= 0):
        SQLHelpers.getInstance().executeUpdate(
            "DELETE from projects.item_tag where item_id=%s", (itemId,))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteItem/<id>', methods=['GET'])
def delete_item(id):
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.items WHERE id = '" + id + "'")
    con.commit()
    con.close()
    try:
        idsList = [id]
        if ES_SYNC_ON:
            deleteEntityDoc('Items', idsList)
    except Exception as ex:
        pass

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemById/<id>', methods=['GET'])
def get_item_by_id(id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.items.*, projects.users.name as user FROM projects.items left join projects.users on projects.items.user_id = projects.users.id  WHERE projects.items.id = '" + id + "'")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemdetail/<id>', methods=['GET'])
def get_item_detail(id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.items.* ,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name  from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.projects on projects.items.project = projects.projects.id WHERE projects.items.id="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateItemCounts/<id>', methods=['PUT'])
def update_item_count(id):
    rows = SQLHelpers.getInstance().executeQuery(
        'select update_count, assign_count, collection from projects.items where id ='+str(id))
    update_count = rows[0][0]
    if update_count == None:
        update_count = 0
    assign_count = rows[0][1]
    if assign_count == None:
        assign_count = 0
    prev_collection = rows[0][2]
    update_count = int(update_count) + 1
    if content.get("collection") != prev_collection:
        val = int(assign_count)+1
        cur.execute('update projects.items set assign_count=%s, update_count=%s where id=%s', (str(
            val), str(update_count), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateItem/<id>', methods=['PUT'])
def update_item(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select STATUS,user_id,project, update_count, assign_count, collection from projects.items where id ='+str(id))
    rows = cur.fetchall()
    previous_status = rows[0][0]
    user_id = rows[0][1]
    previous_project = rows[0][2]
    followupDate = content.get("followup")
    if followupDate is None or followupDate == '':
        followupDate = None

    if (content.get("tagType") is not None and len(content.get("tagType")) > 0):
        cur.execute('UPDATE projects.items SET PROJECT = %s , DATE = NULLIF(%s, \'\')::date , DESCRIPTION = %s , PRIORITY = %s , ESTIMATE = %s, ASSIGNEE = %s , STATUS = %s, TYPE = %s, COLLECTION = %s, ACTUAL = %s, tagType=%s, title=%s, topic=%s, followup = NULLIF(%s, \'\')::date, last_updated=%s, due_date = NULLIF(%s, \'\')::date, epic=%s, ide=%s, blocked=%s WHERE id = %s', (content.get("project"), content.get(
            "date"), content.get("description"), content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), content.get("collection"), content.get("actual"), content.get("tagType"), content.get("title"), content.get("topic"), followupDate, now.strftime("%Y-%m-%d"), content.get("due_date"), content.get("epic"), content.get("ide"), content.get('blocked'), id))
    else:
        cur.execute('UPDATE projects.items SET PROJECT = %s , DATE = NULLIF(%s, \'\')::date , DESCRIPTION = %s , PRIORITY = %s , ESTIMATE = %s, ASSIGNEE = %s , STATUS = %s, TYPE = %s, COLLECTION = %s, ACTUAL = %s, tagType=%s, title=%s, topic=%s, followup = NULLIF(%s, \'\')::date, last_updated=%s, due_date = NULLIF(%s, \'\')::date, epic=%s, ide=%s, blocked=%s WHERE id = %s', (content.get("project"), content.get(
            "date"), content.get("description"), content.get("priority"), content.get("estimate"), content.get("assignee"), content.get("status"), content.get("type"), content.get("collection"), content.get("actual"), [], content.get("title"), content.get("topic"), followupDate, now.strftime("%Y-%m-%d"), content.get("due_date"), content.get("epic"), content.get("ide"), content.get('blocked'), id))

    if content.get('blocked'):
        rows = SQLHelpers.getInstance().executeRawResult(
            'select item_id, description from projects.items where id ='+str(id))
        ref_id = rows[0][0]
        description = rows[0][1]
        li = []
        li.append(int(content.get("project")))
        SQLHelpers.getInstance().executeUpdate('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information, activity_id, reference_id, reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                               (li, user_id, ref_id+" marked as Blocked", ref_id, now, now.strftime("%I:%M %p"), description, '9', id, 'I', 'Item Updated'))

    if content.get("status") == 6:
        cur.execute(
            'UPDATE projects.items SET date_close = %s WHERE id = %s', (now, id))
        cur.execute('UPDATE projects.projects SET last_closed_date = %s WHERE id = %s',
                    (now, content.get("project")))
    elif content.get("status") == 3:
        cur.execute(
            'UPDATE projects.items SET inprogress_date = %s WHERE id = %s', (now, id))
    elif content.get("status") == 5:
        cur.execute(
            'UPDATE projects.items SET completed_date = %s WHERE id = %s', (now, id))
    else:
        cur.execute(
            'UPDATE projects.items SET date_close = NULL WHERE id = %s', (id,))

    if content.get("status") != previous_status:
        cur.execute('Insert into projects.ITEMS_Comment_status  (items_id, status, date, user_id) values(%s,%s,%s,%s)',
                    (id, content.get("status"), content.get("date"), user_id))
    if previous_project != content.get("project"):
        cur.execute('select item_count,prefix from projects.projects where id =' +
                    str(content.get("project")))
        rows = cur.fetchall()
        count = rows[0][0]
        prefix = rows[0][1]
        item_id = prefix + "-" + str(count+1)
        cur.execute(
            'UPDATE projects.items SET ITEM_ID = %s WHERE id = %s', (item_id, id))
        cur.execute('UPDATE projects.projects SET item_count = %s WHERE id = %s',
                    (count+1, content.get("project")))
        cur.execute('UPDATE projects.collections SET last_activity= %s WHERE id = %s',
                    (now, content.get('collection')))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateItemCollection/<id>', methods=['PUT'])
def update_item_collection(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    listA = []
    for items in content.get("previousItems"):
        if items in content.get("items"):
            pass
        else:
            listA.append(items)
    cur.execute(
        'UPDATE projects.items SET collection = %s WHERE id = any(%s)', (None, listA))

    cur.execute('UPDATE projects.items SET collection = %s WHERE id = any(%s)',
                (id, content.get("items")))
    cur.execute('UPDATE projects.collections SET last_activity= %s WHERE id = %s',
                (now.strftime("%m-%d-%Y %I:%M %p"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateItemCollectionSingle/<id>/<itemId>/<cType>', methods=['PUT'])
def update_item_collection_single(id, itemId, cType):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if cType == "set":
        cur.execute('UPDATE projects.items SET collection = %s WHERE id = %s',
                    (id, itemId))
    else:
        cur.execute(
            'UPDATE projects.items SET collection = %s WHERE id = %s', (None, itemId))

    cur.execute('UPDATE projects.collections SET last_activity= %s WHERE id = %s',
                (now.strftime("%m-%d-%Y %I:%M %p"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/register', methods=['POST'])
def register_user():
    content = request.get_json(silent=True)
    hased_password = generate_password_hash(
        content['password'], method='sha256')
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("INSERT INTO projects.users (USERNAME, PASSWORD,INVITE_ID,TYPE,NAME) VALUES (%s, %s,%s,%s,%s) RETURNING id",
                (content.get("username"), hased_password, content.get("inviteId"), content.get("type"), content.get("name")))
    con.commit()
    rows = cur.fetchall()
    id = rows[0][0]
    cur.execute("update projects.invite set accepted= 'Accepted' where id =" +
                str(content.get("inviteId")))
    con.commit()
    cur.execute("select project,user_id from projects.invite where id =" +
                str(content.get("inviteId")))
    rows = cur.fetchall()
    project = rows[0][0]
    invite_by = rows[0][1]
    cur.execute("INSERT INTO projects.user_project_mapping (user_id,project,invite_by) VALUES (%s, %s,%s)",
                (id, project, invite_by))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Users', 'users', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/registerWithoutInvite', methods=['POST'])
def register_user_without_invite():
    content = request.get_json(silent=True)
    hased_password = generate_password_hash(
        content['password'], method='sha256')
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("INSERT INTO projects.users (USERNAME, PASSWORD,INVITE_ID,TYPE,NAME) VALUES (%s, %s,%s,%s,%s) RETURNING id",
                (content.get("username"), hased_password, content.get("inviteId"), content.get("type"), content.get("name")))
    con.commit()
    rows = cur.fetchall()
    id = rows[0][0]
    # cur.execute("update projects.invite set accepted= 'Accepted' where id ="+str(content.get("inviteId")))
    # con.commit()
    # cur.execute("select project,user_id from projects.invite where id ="+str(content.get("inviteId")))
    # rows = cur.fetchall()
    # project = rows[0][0]
    # invite_by = rows[0][1]
    # cur.execute("INSERT INTO projects.user_project_mapping (user_id,project,invite_by) VALUES (%s, %s,%s)", (id,project,invite_by))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Users', 'users', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/login', methods=['POST'])
def login():
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.users WHERE LOWER(username) =LOWER('" +
                content.get("username")+"')")
    rows = cur.fetchall()
    con.close()
    if len(rows) < 1:
        return jsonify({'code': "401", 'error': 'User not exist!'})
    else:
        response = {"id": rows[0][0], "username": rows[0][1], "password": rows[0][2],
                    "expiryDate": rows[0][3], "name": rows[0][6], "profileImage": rows[0][7]}

        app.logger.info("account_user.expiryDate ==> %s",
                        response['expiryDate'])
        if response['expiryDate'] != None:
            dateTime1 = datetime.strptime(response['expiryDate'], "%Y-%m-%d")
            today = date.today()
            dateTime2 = datetime.strptime(str(today), "%Y-%m-%d")
            app.logger.info("data 1 --> %s,%s", dateTime1, dateTime2)

        if response['expiryDate'] != None and dateTime2 > dateTime1:
            return jsonify({'code': "402", 'error': 'User account expire'})

        elif check_password_hash(response['password'], content.get("password")):
            app.logger.info("Session in login ==> %s", session)
            return jsonify({'code': "200", 'message': "success", 'id': response['id'], "name": response['name'], "image": response["profileImage"]})

    return jsonify({'code': "401", 'error': 'Entered password is wrong!'})


@endpointV2.route('/v2/checkCurrentPassword', methods=['POST'])
def check_current_password():
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT password FROM projects.users WHERE username ='" +
                content.get("username")+"'")
    rows = cur.fetchall()
    if check_password_hash(rows[0][0], content.get("password")):
        hased_password = generate_password_hash(
            content['newPassword'], method='sha256')
        cur.execute("update projects.users set password= %s WHERE username =%s",
                    (hased_password, content.get("username")))
        con.commit()
        con.close()
        return jsonify({'code': "200", 'message': True})
    else:
        return jsonify({'code': "200", 'message': False})

# @endpointV2.route('/v2/updatePassword', methods=['POST'])
# def update_password():
#     content = request.get_json(silent=True)
#     configuration = AdminConfiguration.objects().first()
#     hased_password = generate_password_hash(content['password'],method='sha256')
#     con = psycopg2.connect(database= configuration.database, user=configuration.user, password=configuration.password, host=configuration.host, port=configuration.port)
#     cur = con.cursor()
#     cur.execute("update projects.users set password=%s WHERE username ='%s'"(hased_password, content.get("username")))
#     rows = cur.fetchall()
#     con.close()
#     return jsonify({'code':"200",'message': "Success" })


@endpointV2.route('/v2/setItemComment/<itemId>', methods=['POST'])
def set_item_comment(itemId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.items_attachment (ITEMS_ID,COMMENT,ATTACHMENT, DATE, user_by) VALUES (%s, %s, %s,%s, %s ) RETURNING id',
                (itemId, content.get("comment"), "",  datetime.today().strftime('%Y-%m-%d'), content.get("userid")))
    con.commit()
    rows = cur.fetchall()
    try:
        idList = [rows[0][0]]
        if ES_SYNC_ON:
            indexEntityDoc('Attachments', 'items_attachment', 'id', idList)
    except Exception as ex:
        pass
    con.close()

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setItemAttachment/<itemId>', methods=['POST'])
def set_item_attachment(itemId):
    content = request.form
    now = datetime.now()
    attachment = None
    file_size = None
    attIds = []
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"attachments/" +
             itemId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            allFiles = request.files.getlist("file")
            for sFile in allFiles:
                sFilename = sFile.filename
                attachment = sFilename[:sFilename.rindex(
                    ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
                sFile.save(os.path.join(
                    app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/", attachment))
                S3Client.upload_file(os.path.join(
                    app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/", attachment), "items/attachments/"+itemId+"/"+attachment)
                file_size = os.stat(
                    app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/" + attachment).st_size
                if content.get("comment") is not None and content.get("comment") != "":
                    comment = content.get("comment")
                else:
                    comment = ""
                rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items_attachment (ITEMS_ID,COMMENT,ATTACHMENT, DATE, INTERNAL_CHECK_BOX, USER_BY, att_size) VALUES (%s, %s, %s,%s, %s, %s, %s) RETURNING id',
                                                              (itemId, comment, attachment, now.strftime("%m-%d-%Y %I:%M %p"), content.get('internalCheckbox'), content.get("userId"), file_size))
                attIds.append(rows[0][0])
    else:
        rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items_attachment (ITEMS_ID,COMMENT,ATTACHMENT, DATE, INTERNAL_CHECK_BOX, USER_BY) VALUES (%s, %s, %s,%s, %s, %s) RETURNING id',
                                                      (itemId, content.get("comment"), "", now.strftime("%m-%d-%Y %I:%M %p"), content.get('internalCheckbox'), content.get("userId")))
        attIds.append(rows[0][0])
    try:
        if ES_SYNC_ON:
            indexItemAttachmentDocs(attIds)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/uploadUserTempAttachment/<userId>', methods=['POST'])
def upload_user_temp_attachment(userId):
    content = request.form
    now = datetime.now()
    attachment = None
    attachments = []
    att_size = []
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"temp/"+userId +
             "/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            allFiles = request.files.getlist("file")
            # app.logger.info("multiple file attachment:: %s", allFiles)
            for sFile in allFiles:
                sFilename = sFile.filename
                attachment = sFilename[:sFilename.rindex(
                    ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
                app.logger.info("attachment file name:: %s", attachment)
                sFile.save(os.path.join(
                    app.config['UPLOAD_FOLDER']+"temp/"+userId+"/", attachment))
                path = app.config['UPLOAD_FOLDER'] + \
                    "temp/"+userId+"/" + attachment
                file_size = os.stat(path).st_size
                att_size.append(file_size)
                attachments.append(attachment)
    else:
        attachment = ""
        att_size = ""

    return jsonify({'code': "200", 'message': "success", "attachmentName": attachments, "att_size": att_size})


@endpointV2.route('/v2/getItemAttachments/<itemId>', methods=['GET'])
def get_items_attachment(itemId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.items_attachment.*,PROJECTS.USERS.name as username FROM projects.items_attachment left join PROJECTS.ITEMS on PROJECTS.ITEMS.id = projects.items_attachment.ITEMS_ID left join PROJECTS.USERS on PROJECTS.USERS.id = PROJECTS.items_attachment.user_by   WHERE ITEMS_ID ="+itemId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionAttachments/<collectionId>', methods=['GET'])
def get_collection_attachment(collectionId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "SELECT * from projects.collection_attachment  WHERE collection_id ="+collectionId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getStatusList/<id>', methods=['GET'])
def get_status_list(id):
    finalResponse = []

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+") and "
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") and "
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id ="+str(id)+" and "
        else:
            query = "where "

    cur.execute("SELECT s.*, s.id as stat_id , (select count(*) from projects.items " +
                query+" status = s.id ) FROM projects.status s ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getPriorityList', methods=['GET'])
def get_priority_list():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.priority ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTypeList', methods=['GET'])
def get_type_list():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.type ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMethodologyList', methods=['GET'])
def get_methodology_list():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.methodology ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/sendItemEmail/<email>', methods=['POST'])
def send_email(email):
    bodyData = []
    columnValue = []
    content = request.get_json()
    filename = "items.xlsx"
    Path(app.config['UPLOAD_FOLDER'] +
         "attachments/").mkdir(parents=True, exist_ok=True)
    columnList = content.get('columnDef')
    for item in columnList:
        columnValue.append(item['tableColumnName'])
    if(content.get('emailData') == "attachment"):
        wb = Workbook()
        sheet1 = wb.add_sheet('Sheet 1')
        index = 0
        for item in columnList:
            sheet1.write(0, index, item['columnDisplayName'])
            index = index+1

        for i, row in enumerate(content.get('body')):
            firstIndex = i+1
            for index, item in enumerate(columnValue):
                sheet1.write(firstIndex, index, row[item])

        wb.save(os.path.join(
            app.config['UPLOAD_FOLDER']+"attachments/", filename))
    else:
        bodyData = content.get('body1').split('\n')
        html1 = ""
        for i in bodyData:
            html1 += "<p>"+i+"<p><br\>"
        css = 'style="padding:5px; font-family: Arial,sans-serif; font-size: 16px; line-height:20px;line-height:30px;"'

        html = '<table width="100%" cellpadding="0" cellspacing="0" style="min-width:100%;border:1px solid #333;"><thead><tr>'
        for item in columnList:
            html += '<th scope="col" '+css+'>' + \
                item['columnDisplayName']+'</th>'
        html += '</tr></thead><tbody>'
        for i, row in enumerate(content.get('body')):
            html += "<tr>"
            for item in columnValue:
                if item == 'description':
                    html += "<td valign='top' style='padding:5px; font-family: Arial,sans-serif; font-size: 16px; line-height:20px;border:1px solid #333;'>" + \
                        str(row[item].encode('utf-8')) + "</td>"
                else:
                    html += "<td valign='top' style='padding:5px; font-family: Arial,sans-serif; font-size: 16px; line-height:20px;border:1px solid #333;'>" + \
                        str(row[item]) + "</td>"
            html += "</tr>"
        html += "</tbody></table>"

    msg = Message(
        content.get('subject'),
        sender=('Istoria Team', mailSender),
        recipients=[email]
    )
    filepath = r''+app.config['UPLOAD_FOLDER']+"attachments"+"/"+filename

    if(content.get('emailData') == "attachment"):
        msg.body = content.get('body1')
        with app.open_resource(filepath) as fp:
            msg.attach(filename, "application/octect-stream", fp.read())
    else:
        msg.html = html1 + " " + html
    # app.logger.info(" MSG ==> %s",msg)
    mail.send(msg)
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setItemTag/<itemId>/<userId>', methods=['POST'])
def set_item_tag(itemId, userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.item_tag (ITEM_ID,USER_ID,DATE) VALUES (%s,%s, %s)',
                (itemId, userId, datetime.today().strftime('%Y-%m-%d')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteItemTag/<id>', methods=['GET'])
def delete_item_tag(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.item_tag WHERE id = '" + id + "'")
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getAllTags/<id>', methods=['GET'])
def get_items_tag(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select PROJECTS.ITEM_TAG.id as tag_id,projects.projects.project_name,PROJECTS.ITEM_TAG.date as tag_date, projects.items.*,(SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype),PROJECTS.ITEM_TAG.user_id as userid ,projects.collections.collection as collection_name,PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from PROJECTS.ITEM_TAG left join projects.items on PROJECTS.ITEM_TAG.item_id = projects.items.id left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type on projects.items.type = PROJECTS.type.id left join projects.projects on projects.items.project = projects.projects.id left join projects.collections on projects.items.collection = projects.collections.id  where projects.item_tag.user_id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getDataAttachment/<id>', methods=['GET'])
def get_data_attachment(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select PROJECTS.ITEMS_attachment.*,projects.projects.project_name,PROJECTS.USERS.name as username, projects.items.project, projects.items.description,projects.items.item_id, projects.items.id as primary_item_id from PROJECTS.ITEMs_attachment left join projects.items on PROJECTS.ITEMS_attachment.items_id = projects.items.id left join projects.users on projects.ITEMS_attachment.USER_BY = projects.users.id left join projects.projects on projects.items.project = projects.projects.id  where attachment <> '' and projects.users.id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteItemAttachment/<id>', methods=['GET'])
def delete_item_attachment(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.items_attachment WHERE id = '" + id + "'")
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            deleteEntityDoc('Attachments', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getAttachmentExist', methods=['GET'])
def get_attachment_exist():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select distinct(items_id) from projects.items_attachment order by items_id;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getDataComment/<id>', methods=['GET'])
def get_data_comment(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "and projects.projects.created_by ="+str(id)+" or projects.projects.created_by="+str(
            inviteUserId)+" and projects.projects.id = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "and projects.projects.created_by =" + \
                str(id)+" or projects.projects.id = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "and projects.projects.created_by ="+str(id)
        else:
            query = ""

    cur.execute("select PROJECTS.ITEMS_attachment.*,PROJECTS.USERS.name as username,projects.projects.project_name,projects.users.name, projects.items.project, projects.items.description,projects.items.item_id, projects.items.id as primary_item_id from PROJECTS.ITEMs_attachment left join projects.items on PROJECTS.ITEMS_attachment.items_id = projects.items.id left join projects.users on projects.items_attachment.user_by  = projects.users.id left join projects.projects on projects.items.project = projects.projects.id  where comment <> '' "+query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllProjects/<id>', methods=['GET'])
def get_project(id):
    finalResponse = []
    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.projects.created_by ="+str(id)+" or projects.projects.created_by="+str(
            inviteUserId)+" and projects.projects.id = ANY(Array"+str(projectArr)+")"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.projects.created_by =" + \
                str(id)+" or projects.projects.id = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.projects.created_by ="+str(id)
        else:
            query = ""
    finalResponse = SQLHelpers.getInstance().executeQuery("SELECT projects.projects.* ,(SELECT array_agg(u.team) as team_name FROM unnest(projects.projects.team) project LEFT JOIN projects.teams u on u.id = project), (select date from projects.items where project = projects.projects.id order by id desc limit 1) as last_item, ( select count(*) from projects.items where project = projects.projects.id and status != 6) as open, ( select count(*) from projects.items where projects.items.priority = 2 and project = projects.projects.id) as low, ( select count(*) from projects.items where projects.items.priority = 3 and project = projects.projects.id) as medium, ( select count(*) from projects.items where projects.items.priority = 4 and project = projects.projects.id) as high, (select count(*) from projects.collections where projects.projects.id = Any(projects.collections.projects)) as collection ,projects.methodology.name as methodology_name FROM projects.projects left join projects.methodology on projects.projects.methodology_id = projects.methodology.id "+query)

    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllProjectsId/<userId>/<id>', methods=['GET'])
def get_project_id(userId, id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.projects.* , ( select count(*) from projects.items where project = projects.projects.id and status != 6) as open, ( select count(*) from projects.items where projects.items.priority = 2 and project = projects.projects.id) as low, ( select count(*) from projects.items where projects.items.priority = 3 and project = projects.projects.id) as medium, ( select count(*) from projects.items where projects.items.priority = 4 and project = projects.projects.id) as high,projects.methodology.name as methodology_name FROM projects.projects left join projects.methodology on projects.projects.methodology_id = projects.methodology.id where projects.projects.created_by ="+userId + " and projects.projects.id="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setProject/<userId>', methods=['POST'])
def set_project(userId):
    now = datetime.now()
    content = request.form
    image = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "projects/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"projects/", scriptFile.filename))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"projects/", scriptFile.filename), "projects/"+scriptFile.filename)
        image = scriptFile.filename
    else:
        image = ""

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.projects (CREATED_BY, PROJECT_NAME, DESCRIPTION, PREFIX, NEXTITEM, METHODOLOGY_ID, TEAM, Assignee, IMAGE, creation_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id',
                (userId, content.get("project"), content.get("description"), content.get("prefix"), content.get("nextItem"), content.get("methodology"), content.get('team'), content.get('assignee'), image, now))
    con.commit()
    rows = cur.fetchall()
    id = rows[0][0]
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Projects', 'projects', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/deleteProject/<id>', methods=['GET'])
def delete_project(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.projects WHERE id = '" + id + "'")
    con.commit()
    # rows = cur.fetchall()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            deleteEntityDoc('Projects', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getProjectById/<id>', methods=['GET'])
def get_project_by_id(id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.projects WHERE id = '" + id + "'")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateProject/<id>/<userId>', methods=['PUT'])
def update_project(id, userId):
    content = request.form
    image = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "projects/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"projects/", scriptFile.filename))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"projects/", scriptFile.filename), "projects/"+scriptFile.filename)
        image = ", image = '" + scriptFile.filename+"'"
    else:
        image = ""

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('UPDATE projects.projects SET project_name = %s , description = %s , prefix = %s , nextitem = %s ,assignee = %s '+image+', methodology_id = %s WHERE id = %s',
                (content.get("project"), content.get("description"), content.get("prefix"), content.get("nextItem"), content.get("assignee"), content.get("methodology"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Projects', 'projects', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateProjectTeam/<id>', methods=['PUT'])
def update_project_team(id):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate(
        "update projects.projects SET team=%s where id =%s", (content.get('team'), id))
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Projects', 'projects', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/saveCollectionProject/<id>', methods=['PUT'])
def saveCollectionProject(id):
    content = request.get_json(silent=True)
    now = datetime.now()
    li = []
    li.append(int(id))
    idsList = []
    for item in content.get('data'):
        rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.collections (collection, DESCRIPTION, from_date, to_date, projects, status, last_activity) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id',
                                                      (item["collection"], item["description"], item["from_date"], item["to_date"], li, item['status'], now.strftime("%m-%d-%Y %I:%M %p")))
        idsList.append(rows[0][0])
    try:
        if ES_SYNC_ON:
            indexEntityDoc('Collections', 'collections', 'id', idsList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getProjectImage/<fileName>/<userId>', methods=['GET'])
def get_project_image(fileName, userId):
    if fileName is None or fileName == 'undefined':
        return ""

    mimeType = mimetypes.MimeTypes().guess_type(fileName)[0]
    s3FileObj = S3Client.get_object("projects/"+fileName)

    return Response(s3FileObj['Body'].read(), content_type=mimeType)

    # return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"projects/", filename=fileName)


@endpointV2.route('/v2/getProjectList/<id>', methods=['GET'])
def get_project_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = " where projects.projects.created_by ="+str(id)+" or projects.projects.created_by ="+str(
            inviteUserId)+" and projects.projects.id = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.projects.created_by =" + \
                str(id)+" or projects.projects.id = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.projects.created_by ="+str(id)
        else:
            query = ""
        # query = ""
    cur.execute("select id, project_name, (select count(*) from projects.items where status = 1 and project = projects.projects.id) from projects.projects "+query + " order by project_name")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getContactList/<id>', methods=['GET'])
def get_contact_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select id, contact from projects.contacts where user_id= " +
                id + " order by contacts")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectCode/<id>/<costType>', methods=['GET'])
def get_project_code(id, costType):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if costType == "cost":
        cur.execute("select id, project_code from PROJECTS.project_code where user_id= " +
                    id + " and cost_item='true' order by project_code")
    if costType == "time":
        cur.execute("select id, project_code from PROJECTS.project_code where user_id= " +
                    id + " and time_item='true' order by project_code")

    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getRepos/<id>', methods=['GET'])
def get_repos(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()

    cur.execute("select id, repo_name from PROJECTS.repo where CREATED_BY= " +
                id + "  order by repo_name")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProviders', methods=['GET'])
def get_providers():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()

    cur.execute("select id, name from PROJECTS.providers  order by name")

    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/checkProjectItemExist/<id>', methods=['GET'])
def check_project_items_exist(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select count(*) from projects.items where project ="+id)
    rows = cur.fetchall()
    exist = None
    if rows[0][0] > 0:
        exist = True
    else:
        exist = False
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/checkProjectCodeExist/<codeName>', methods=['GET'])
def check_project_code_exist(codeName):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select count(*) from projects.project_code where project_code ='"+codeName+"'")
    rows = cur.fetchall()
    exist = None
    if rows[0][0] > 0:
        exist = True
    else:
        exist = False
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/getAssigneeValue/<id>', methods=['GET'])
def get_assignee_value(id):
    finalResponse = []
    rows = SQLHelpers.getInstance().executeRawResult(
        "select assignee from projects.projects where id ="+id)
    value = rows[0][0]
    return jsonify({'code': "200", 'message': "success", "value": value})


@endpointV2.route('/v2/setInvite/<userId>', methods=['POST'])
def set_invite(userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.invite (user_id,email,project,send_on,username,accepted) VALUES (%s,%s, %s,%s,%s,%s) RETURNING id',
                (userId, content.get('email'), content.get('project'), now.strftime("%m-%d-%Y %I:%M %p"), content.get('username'), "Pending"))
    con.commit()
    rows = cur.fetchall()
    id = rows[0][0]
    cur.execute('select projects.users.name as user_name,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project)  from projects.invite left join projects.users on projects.invite.user_id = projects.users.id where projects.invite.id ='+str(id))
    rows = cur.fetchall()
    username = rows[0][0]
    project_name = rows[0][1]
    if project_name != None:
        all_projects = ', '.join(project_name)
    else:
        all_projects = ''
    msg = Message(
        "Invitation to join Istoria",
        sender=('Istoria Team', mailSender),
        recipients=[content.get('email')]
    )
    random = get_random_string(12)
    hash1 = sha256(random.encode()).hexdigest()
    cur.execute(
        'INSERT INTO projects.hash (invite_id, hash_code) values (%s,%s)', (id, hash1))
    con.commit()
    body_html = """ <body<p>Hi,</p>
                    <br>
                    <p>"""+username+""" has invited you to some Istoria Projects. Please click on the link below to sign up:</p>
                    <p>"""+Production.host+"""signUp?id="""+str(hash1)+"""<p>
                    <p>Project(s): <b>"""+all_projects+"""</b><p>
                    <br>
                    <p>To cancel invitation <a href=" """+Production.host+"""signUp?cancelId="""+str(hash1)+""""> please click here</a></p>
                    <p>Please note that the link will expire in 48 hours.</p>
                    <p>Have a wonderful day!</p>
                    <p>Thank you,</p>
                    <p>Istoria Team</p>
                    </body>
                    """
    msg.html = body_html
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateInvite/<id>', methods=['PUT'])
def update_invite(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('select project from projects.invite where id = '+id)
    rows = cur.fetchall()
    unique_list = []
    lastProjects = rows[0][0]
    lastProjects.extend(content.get("project"))
    for x in lastProjects:
        if x not in unique_list:
            unique_list.append(x)
    cur.execute('UPDATE projects.invite SET  project = %s , send_on = %s , username = %s WHERE id = %s',
                (unique_list, now.strftime("%m-%d-%Y %I:%M %p"), content.get("username"), id))
    con.commit()
    cur.execute('select projects.users.name as user_name,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project)  from projects.invite left join projects.users on projects.invite.user_id = projects.users.id where projects.invite.id ='+str(id))
    rows = cur.fetchall()
    username = rows[0][0]
    project_name = rows[0][1]
    if project_name != None:
        all_projects = ', '.join(project_name)
    else:
        all_projects = ''
    msg = Message(
        "Invitation to join Istoria",
        sender=('Istoria Team', mailSender),
        recipients=[content.get('email')]
    )
    random = get_random_string(12)
    hash1 = sha256(random.encode()).hexdigest()
    cur.execute(
        'update projects.hash set hash_code = %s where invite_id = %s', (hash1, id))
    con.commit()
    body_html = """ <body<p>Hi,</p>
                    <br>
                    <p>"""+username+""" has invited you to some Istoria Projects. Please click on the link below to sign up:</p>
                    <p>"""+Production.host+"""signUp?id="""+str(hash1)+"""<p>
                    <p>Project(s): <b>"""+all_projects+"""</b><p>
                    <br>
                    <p>To cancel invitation <a href=" """+Production.host+"""signUp?cancelId="""+str(hash1)+""""> please click here</a></p>
                    <p>Please note that the link will expire in 48 hours.</p>
                    <p>Have a wonderful day!</p>
                    <p>Thank you,</p>
                    <p>Istoria Team</p>
                    </body>
                    """
    msg.html = body_html
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


def get_random_string(length):
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


@endpointV2.route('/v2/getInviteList/<userId>', methods=['GET'])
def get_invite_list(userId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.invite.* , projects.users.username as user_name,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project)  from projects.invite left join projects.users on projects.invite.user_id = projects.users.id where user_id ="+userId+" order by projects.invite.id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getRecievedList/<userId>', methods=['GET'])
def get_recieved_list(userId):
    finalResponse = []
    rows = SQLHelpers.getInstance().executeRawResult(
        "select username from projects.users where id = '"+userId+"'")
    email = rows[0][0]
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.invite.* , projects.users.name as sender_name,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project)  from projects.invite left join projects.users on projects.invite.user_id = projects.users.id where projects.invite.email ='"+str(email)+"' order by projects.invite.id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getInviteById/<id>', methods=['GET'])
def get_invite_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.invite where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getInviteId/<hash>', methods=['GET'])
def get_inviteId_hash(hash):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select invite_id from projects.hash where hash_code ='"+str(hash)+"'")
    rows = cur.fetchall()
    if len(rows) < 1:
        resp = False
        id = ""
    else:
        resp = True
        id = rows[0][0]
    con.close()
    return jsonify({'code': "200", 'message': "success", "id": id, "resp": resp})


@endpointV2.route('/v2/checkInviteEmailExist/<email>/<userId>', methods=['GET'])
def check_invite_email_exist(email, userId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select id from projects.invite where email ='" +
                email+"' and user_id="+userId)
    rows = cur.fetchall()
    exist = None
    if len(rows) > 0:
        exist = True
        id = rows[0][0]
    else:
        exist = False
        id = ""
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": exist, "id": id})


@endpointV2.route('/v2/checkUserEmailExist/<email>/<i_id>', methods=['GET'])
def check_user_email_exist(email, i_id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select id from projects.users where username ='"+email+"'")
    rows = cur.fetchall()
    exist = None
    if len(rows) > 0:
        exist = True
        id = rows[0][0]
        cur.execute("select project from projects.invite where id = "+str(i_id))
        rows = cur.fetchall()
        projects = rows[0][0]
        cur.execute(
            "update projects.user_project_mapping set project =%s  where user_id =%s", (projects, id))
        con.commit()
    else:
        exist = False
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/sendSignupEmail', methods=['POST'])
def send_signup_mail():
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.user_project_mapping.project) project LEFT JOIN projects.projects u on u.id = project) from projects.user_project_mapping where user_id ="+str(content.get('id')))
    rows = cur.fetchall()
    projects = rows[0][0]
    all_projects = ', '.join(projects)
    msg = Message(
        "Sign Up Confirmation",
        sender=('Istoria Team', mailSender),
        recipients=[content.get('username')]
    )
    body = "Hello "+content.get('name')+",\n\nThank you for signing up in Istoria. Sign up account details were given below.\n\nUsername : " + \
        content.get('username')+"\nProjects Allocated : "+all_projects + \
        " \n\nHave a wonderful day!\n\nThank you,\nIstoria Team"
    msg.body = body
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getInviteListAdmin', methods=['GET'])
def get_invite_list_admin():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.users.*,projects.invite.send_on ,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project),(select username from projects.users where id = projects.invite.user_id) as invited_by from projects.users left join projects.invite on projects.users.invite_id = projects.invite.id  where type = 'I' ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteInviteUser/<id>', methods=['DELETE'])
def delete_invite(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.users WHERE id ="+id)
    con.commit()
    # rows = cur.fetchall()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            deleteEntityDoc('Users', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getUserListAdmin', methods=['GET'])
def get_user_admin():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.users where type = 'A' ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setEmail/<userId>', methods=['POST'])
def set_email_data(userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.email (CREATED_BY,email, project, hint, created_on) VALUES (%s, %s, %s, %s, %s)',
                (userId, content.get("email"), content.get("project"), content.get("hint"), content.get("createdOn")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateEmail/<id>', methods=['PUT'])
def update_email_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.email set email=%s, project=%s, hint=%s where id = %s',
                (content.get("email"), content.get("project"), content.get("hint"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getEmailList/<id>', methods=['GET'])
def get_email_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.email.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.email.project) project LEFT JOIN projects.projects u on u.id = project), projects.users.username from projects.email left join projects.users on projects.email.created_by = projects.users.id where created_by ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getEmailById/<id>', methods=['GET'])
def get_email_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.email where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteEmail/<id>', methods=['DELETE'])
def delete_email(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.email WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setDomain/<userId>', methods=['POST'])
def set_domain_data(userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.domain (CREATED_BY,url,ip,instance,service,renews,yearlycost, project, created_on) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)', (userId, content.get(
        "url"), content.get("ip"), content.get("instance"), content.get("service"), content.get("renews"), content.get("yearlyCost"),  content.get("project"), content.get("createdOn")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateDomain/<id>', methods=['PUT'])
def update_domain_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.domain set url=%s, ip=%s, instance=%s, service=%s, renews=%s, yearlycost=%s, project=%s where id =%s', (content.get(
        "url"), content.get("ip"), content.get("instance"), content.get("service"), content.get("renews"), content.get("yearlyCost"),  content.get("project"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getDomainList/<id>', methods=['GET'])
def get_domain_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.domain.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.domain.project) project LEFT JOIN projects.projects u on u.id = project), projects.users.username from projects.domain left join projects.users on projects.domain.created_by = projects.users.id where created_by ="+id+" order by id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getDomainById/<id>', methods=['GET'])
def get_domain_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.domain where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteDomain/<id>', methods=['DELETE'])
def delete_domain(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.domain WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setCloud/<userId>', methods=['POST'])
def set_cloud_data(userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.cloud (CREATED_BY, project, account, provider, monthly_cost, free_time, created_on) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (userId, content.get("project"), content.get("account"), content.get("provider"), content.get("monthly_cost"), content.get("free_time"), content.get("createdOn")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateCloud/<id>', methods=['PUT'])
def update_cloud_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.cloud set project=%s, account=%s, provider=%s, monthly_cost=%s, free_time=%s where id = %s', (content.get(
        "project"), content.get("account"), content.get("provider"), content.get("monthly_cost"), content.get("free_time"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCloudList/<id>', methods=['GET'])
def get_cloud_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.cloud.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.cloud.project) project LEFT JOIN projects.projects u on u.id = project), projects.users.username from projects.cloud left join projects.users on projects.cloud.created_by = projects.users.id where created_by ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCloudById/<id>', methods=['GET'])
def get_cloud_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.cloud where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteCloud/<id>', methods=['DELETE'])
def delete_cloud(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.cloud WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setInstance/<userId>', methods=['POST'])
def set_instance_data(userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.instance (CREATED_BY, cloudaccount, instancetype, project ,instance_id, url, ip, created_on) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)', (userId,
                                                                                                                                                                              content.get("cloudAccount"), content.get("instanceType"), content.get("project"), content.get("instance_id"), content.get("url"), content.get("ip"), content.get("createdOn")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateInstance/<id>', methods=['PUT'])
def update_instance_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.instance set cloudaccount=%s, instancetype=%s, project=%s ,instance_id=%s, url=%s, ip=%s where id = %s', (content.get(
        "cloudAccount"), content.get("instanceType"), content.get("project"), content.get("instance_id"), content.get("url"), content.get("ip"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getInstanceList/<id>', methods=['GET'])
def get_instance_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.instance.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.instance.project) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.account) as cloud_name FROM unnest(projects.instance.cloudaccount) item LEFT JOIN projects.cloud u on u.id = item), projects.users.username from projects.instance left join projects.users on projects.instance.created_by = projects.users.id where created_by ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getInstanceById/<id>', methods=['GET'])
def get_instance_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.instance where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteInstance/<id>', methods=['DELETE'])
def delete_instances(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.instance WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setGit/<userId>', methods=['POST'])
def set_git_data(userId):
    content = request.get_json(silent=True)
    app.logger.info("repo::::::::::::::::::%s", content.get("repos"))
    #configuration = AdminConfiguration.objects().first()
    #con = psycopg2.connect(database= configuration.database, user=configuration.user, password=configuration.password, host=configuration.host, port=configuration.port)
    #cur = con.cursor()
    rows = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.git (CREATED_BY, gitaccount, provider,owner,userId,token,monthly_cost,repos, project ,description,created_on) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,%s, %s, %s) RETURNING id', (userId,
                                                                                                                                                                                                                                                         content.get("gitAccount"), content.get("provider"), content.get("owner"), content.get("userId"), content.get("token"), content.get("monthly_cost"), content.get("repos"), content.get("project"), content.get("description"), content.get("createdOn")))
    id = rows[0][0]
    return jsonify({'code': "200", 'message': id})


@endpointV2.route('/v2/updateGit/<id>', methods=['PUT'])
def update_git_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.git set gitaccount=%s, provider=%s,owner=%s,userId=%s,token=%s,monthly_cost=%s,repos=%s, project=%s, description=%s where id =%s', (content.get("gitAccount"), content.get(
        "provider"), content.get("owner"), content.get("userId"), content.get("token"), content.get("monthly_cost"), content.get("repos"), content.get("project"), content.get("description"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getGitList/<id>', methods=['GET'])
def get_git_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.git.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.git.project) project LEFT JOIN projects.projects u on u.id = project),(SELECT array_agg(u.repo_name) as repoName FROM unnest(projects.git.repos) repos LEFT JOIN projects.repo u on u.id = repos), projects.users.username,pro.name as providerName from projects.git left join projects.users on projects.git.created_by = projects.users.id  left join PROJECTS.providers pro on pro.id= projects.git.provider where projects.git.created_by ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getGitById/<id>', methods=['GET'])
def get_git_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.git where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getGitByName/<name>', methods=['GET'])
def getGitByName(name):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.git where gitaccount ='"+name+"'")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteGit/<id>', methods=['DELETE'])
def delete_git(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.git WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setRepo/<userId>', methods=['POST'])
def set_repo_data(userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.repo (CREATED_BY, gitaccount, repo_name, stack, project ,created_on) VALUES (%s, %s, %s, %s, %s, %s)',
                (userId, content.get("gitAccount"), content.get("repo_name"), content.get("stack"), content.get("project"), content.get("createdOn")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateRepo/<id>', methods=['PUT'])
def set_update_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.repo set gitaccount=%s, repo_name=%s, stack=%s, project=%s where id =%s',
                (content.get("gitAccount"), content.get("repo_name"), content.get("stack"), content.get("project"), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getRepoList/<id>', methods=['GET'])
def get_repo_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.repo.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.repo.project) project LEFT JOIN projects.projects u on u.id = project), projects.users.username from projects.repo left join projects.users on projects.repo.created_by = projects.users.id where created_by ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getRepoById/<id>', methods=['GET'])
def get_repo_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.repo where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteRepo/<id>', methods=['DELETE'])
def delete_repo(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.repo WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/changeInviteProject/<id>', methods=['PUT'])
def change_invite_project(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('select id,username from projects.users where invite_id ='+id)
    rows = cur.fetchall()
    user_id = rows[0][0]
    email = rows[0][1]
    cur.execute("update projects.user_project_mapping set project =%s  where user_id =%s",
                (content.get("project"), user_id))
    cur.execute('UPDATE projects.invite SET  project = %s , send_on = %s WHERE id = %s',
                (content.get("project"), content.get("sendOn"), id))
    con.commit()
    cur.execute('select projects.users.name as user_name,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.invite.project) project LEFT JOIN projects.projects u on u.id = project)  from projects.invite left join projects.users on projects.invite.user_id = projects.users.id where projects.invite.id ='+str(id))
    rows = cur.fetchall()
    username = rows[0][0]
    project_name = rows[0][1]
    if project_name != None:
        all_projects = ', '.join(project_name)
    else:
        all_projects = ''
    msg = Message(
        "Change in allocated projects",
        sender=('Istoria Team', mailSender),
        recipients=[email]
    )
    body = username + \
        " has changed your allocated Istoria Projects. Projects allowed for you are given below. \nProject(s): " + \
        all_projects+"\n\nHave a wonderful day!\n\nThank you,\nIstoria Team"
    msg.body = body
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getInviteProjectList/<id>', methods=['GET'])
def get_invite_project_list(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        query = " where projects.projects.created_by ="+str(id)
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        if userType == "I":
            query = "WHERE projects.projects.created_by ="+str(id)
        else:
            query = ""
    cur.execute("select id, project_name from projects.projects " +
                query + " order by project_name")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCopyLinkProjects', methods=['POST'])
def get_copy_link_projects():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            html += """<td>""" + str(row[item]) + """</td>"""
        html += """</tr>"""

    html_str = """<head>
    <meta http-equiv="pragma" content="no-cache" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.21/css/jquery.dataTables.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/1.6.2/css/buttons.dataTables.min.css">
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
</head>
    <h2 style="text-align:center">"""+name + """</h2></div><br>
    <table id="table_id" class="display">
    <thead>
        <tr>
        """ + columnHtml + """
        </tr>
        <thead>
        <tbody>""" + html + """<tbody></table>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.10.21/js/jquery.dataTables.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/dataTables.buttons.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.flash.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/pdfmake.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/vfs_fonts.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.3/jszip.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.html5.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.print.min.js"></script>
        <script type="text/javascript">$(document).ready( function () {
    $('#table_id').DataTable({
        dom: 'Blfrtip',
        buttons: [
            {
                extend: 'excel',
                title: '"""+name + """'
            },
            {
                extend: 'pdf',
                title: '"""+name + """',
                orientation : 'landscape',
                pageSize : 'LEGAL',
            }
        ]
    });
} );</script>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "copiedFile/html/").mkdir(parents=True, exist_ok=True)

    filepath = r''+app.config['UPLOAD_FOLDER'] + \
        "copiedFile/html/"+content.get('fileName')+".html"
    with open(filepath, "w") as file:
        file.write(html_str)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setCollection', methods=['POST'])
def set_collection():
    now = datetime.now()
    content = request.form
    image = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "collections/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"collections/", scriptFile.filename))
        image = scriptFile.filename
    else:
        image = ""

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    project_list = content.get("project").split(",")
    li = []
    for i in project_list:
        li.append(int(i))
    cur.execute('INSERT INTO projects.collections (collection, DESCRIPTION, from_date, to_date, projects, status, upload_file, last_activity) VALUES (%s, %s, NULLIF(%s, \'\')::date, NULLIF(%s, \'\')::date, %s, %s, %s,%s) RETURNING id',
                (content.get("collection"), content.get("description"), content.get("from_date"), content.get("to_date"), li, content.get('status'), image, now.strftime("%m-%d-%Y %I:%M %p")))
    rows = cur.fetchall()
    id = rows[0][0]
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Collections', 'collections', 'id', idList)
            app.logger.info("INDEX REQUEST SUBMITTED...")
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/updateCollection/<id>', methods=['PUT'])
def update_collection(id):
    now = datetime.now()
    content = request.form
    image = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "projects/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"projects/", scriptFile.filename))
        image = ", upload_file = '" + scriptFile.filename+"'"
    else:
        image = ""

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    project_list = content.get("project").split(",")
    li = []
    for i in project_list:
        li.append(int(i))
    cur.execute('UPDATE projects.collections SET collection = %s , description = %s , from_date = NULLIF(%s, \'\')::date , to_date = NULLIF(%s, \'\')::date, projects = %s, status = %s, last_activity= %s, last_updated= %s ' +
                image+' WHERE id = %s', (content.get("collection"), content.get("description"), content.get("from_date"), content.get("to_date"), li, content.get('status'), now.strftime("%m-%d-%Y %I:%M %p"), now.strftime("%Y-%m-%d"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Collections', 'collections', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateCollectionProjects/<id>', methods=['PUT'])
def update_collection_projects(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('UPDATE projects.collections SET projects = %s, last_activity= %s WHERE id = %s',
                (content.get('project'), now.strftime("%m-%d-%Y %I:%M %p"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Collections', 'collections', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteCollection/<id>', methods=['GET'])
def delete_collection(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.collections WHERE id = '" + id + "'")
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            deleteEntityDoc('Collections', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCollectionById/<id>', methods=['GET'])
def get_collection_by_id(id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.collections WHERE id = '" + id + "'")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllCollections/<id>', methods=['GET'])
def get_collections(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
            id)+") or projects.collections.projects && Array"+str(projectArr)
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+") or projects.collections.projects && Array"+str(projectUserList)
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+")"
        else:
            query = ""
    cur.execute("select projects.collections.*, (select sum(actual::numeric) from projects.items where actual != '' and actual is not null and collection = projects.collections.id) as actual_items, (select sum(estimate::numeric) from projects.items where estimate != '' and estimate is not null and collection = projects.collections.id) as estimated_items, (select count(*) from projects.items where NULLIF(estimate, '')::numeric > 0 and NULLIF(actual, '')::numeric > NULLIF(estimate, '')::numeric   and collection = projects.collections.id) as over_estimate, (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as closed_items, (select count(*) from projects.items where status = 7 and collection = projects.collections.id) as qa, (select count(*) from projects.items where status = 5 and collection = projects.collections.id) as completed_items, projects.collection_status.name as status_name, (SELECT array_agg(t.team) filter(where u.team is not null) as teams FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project left join projects.teams t on t.id = Any(u.team) ), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id " + query + " order by projects.collections.last_activity desc Nulls last ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionFilter/<statusId>/<id>', methods=['GET'])
def get_collections_filter(statusId, id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = " projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
            id)+") or projects.collections.projects && Array"+str(projectArr)+" and "
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = " projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+") or projects.collections.projects && Array"+str(projectUserList)+" and "
        elif userType == "I" and pInvite == False:
            query = " projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+" and "
        else:
            query = ""
    cur.execute("select projects.collections.*, (select sum(actual::numeric) from projects.items where actual != '' and actual is not null and collection = projects.collections.id) as actual_items, (select sum(estimate::numeric) from projects.items where estimate != '' and estimate is not null and collection = projects.collections.id) as estimated_items, (select count(*) from projects.items where NULLIF(estimate, '')::numeric > NULLIF(actual, '')::numeric   and collection = projects.collections.id) as over_estimate, (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as closed_items, (select count(*) from projects.items where status = 5 and collection = projects.collections.id) as completed_items, projects.collection_status.name as status_name, (SELECT array_agg(t.team) filter(where u.team is not null) as teams FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project left join projects.teams t on t.id = Any(u.team) ), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id where "+query+" projects.collections.status ="+str(statusId)+" order by projects.collections.last_activity desc Nulls last")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionProjectFilter/<statusId>', methods=['GET'])
def get_collection_project_filter(statusId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.collections.*, (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as completed_items, projects.collection_status.name as status_name, (SELECT array_agg(t.team) filter(where u.team is not null) as teams FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project left join projects.teams t on t.id = Any(u.team) ), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id where "+str(statusId)+" = Any(projects.collections.projects)")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionFilterById/<id>', methods=['GET'])
def get_collection_filter_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.collections.*, (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as completed_items, projects.collection_status.name as status_name, (SELECT array_agg(t.team) filter(where u.team is not null) as teams FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project left join projects.teams t on t.id = Any(u.team) ), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id where projects.collections.id ="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionStatusList/<id>', methods=['GET'])
def get_collection_status(id):
    finalResponse = []

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id =' + id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
            id)+") or projects.collections.projects && Array"+str(projectArr) + " and "
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+") or projects.collections.projects && Array"+str(projectUserList) + " and "
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+") and "
        else:
            query = "where "

    cur.execute("select cs.*, (select count(*) from projects.collections " +
                query+"  status = cs.id  ) from projects.collection_status cs order by id;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsCollection/<id>', methods=['GET'])
def get_item_collections(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.collections.id, (select sum(actual::numeric) from projects.items where collection = projects.collections.id) as total_actual, (select sum(estimate::numeric) from projects.items where collection = projects.collections.id) as total_estimate , (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as closed_items, (select count(*) from projects.items where status = 5 and collection = projects.collections.id) as completed_items, projects.collections.collection as name, projects.collections.status, projects.collections.from_date, projects.collections.to_date,projects.collections.description, projects.collection_status.name as status_name, (select count(*) from projects.items where status = 1 and  collection = projects.collections.id) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id where "+str(id)+" = ANY(projects.collections.projects)  order by projects.collections.from_date asc ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsAsscocited/<id>', methods=['GET'])
def get_associate_items(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.items.id, projects.items.item_id, projects.items.description, projects.items.priority, projects.items.date, projects.items.collection, projects.priority.name as priority_name from projects.items left join projects.priority on projects.items.priority = projects.priority.id where projects.items.project = any( array(select projects from projects.collections where id = "+str(id)+")) and projects.items.status = 1  order by id;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setCollectionAttachment/<collectionId>', methods=['POST'])
def set_collection_attachment(collectionId):
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"attachments/" +
             collectionId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"attachments/"+collectionId+"/", scriptFile.filename))
        attachment = scriptFile.filename
    else:
        attachment = ""

    if content.get("comment") == "":
        comment = "Uploaded Attachment"
    else:
        comment = content.get("comment")

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.collection_attachment (COLLECTION_ID,COMMENT,ATTACHMENT, DATE) VALUES (%s, %s, %s,%s) RETURNING id',
                (collectionId, comment, attachment, now.strftime("%m-%d-%Y %I:%M %p")))
    con.commit()
    rows = cur.fetchall()
    try:
        if ES_SYNC_ON:
            idList = [rows[0][0]]
            indexCollectionAttachmentDocs(idList)
    except Exception as ex:
        pass

    con.close()
    return jsonify({'code': "200", 'message': "success"})


def format_date(value):
    x = value.split("-")
    return x[1]+"-"+x[2]+"-"+x[0]


def listToStringWithoutBrackets(list1):
    return list1.replace('[', '').replace(']', '').replace("'", "")


@endpointV2.route('/v2/downloadPdfCollection/<collection>', methods=['GET'])
def downloadPdfCollection(collection):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"collection/pdf/", filename="collection2.pdf")


@endpointV2.route('/v2/downloadPdfItems/<item>', methods=['GET'])
def downloadPdfItem(item):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"item/pdf/", filename="items.pdf")


@endpointV2.route('/v2/getItemStatusComment/<id>', methods=['GET'])
def get_item_status(id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select PROJECTS.ITEMS_Comment_status.*, projects.users.username, projects.status.name as status_name from PROJECTS.ITEMS_Comment_status left join projects.users on PROJECTS.ITEMS_Comment_status.user_id = projects.users.id left join projects.status on PROJECTS.ITEMS_Comment_status.status = projects.status.id  where PROJECTS.ITEMS_Comment_status.items_id ="+str(id)+" order by PROJECTS.ITEMS_Comment_status.id")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateCollectionStatus/<status>/<id>', methods=['PUT'])
def update_collection_status(status, id):
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('UPDATE projects.collections SET status = %s, last_activity = %s WHERE id = %s',
                (status, now.strftime("%m-%d-%Y %I:%M %p"), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexEntityDoc('Collections', 'collections', 'id', idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateItemAttachment/<itemId>/<id>', methods=['POST'])
def update_item_attachment(itemId, id):
    content = request.form
    now = datetime.now()
    attachment = None
    file_size = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"attachments/" +
             itemId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/", scriptFile.filename))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/", scriptFile.filename), "items/attachments/"+itemId+"/"+scriptFile.filename)
            file_size = os.stat(
                app.config['UPLOAD_FOLDER']+"attachments/"+itemId+"/" + scriptFile.filename).st_size
            attachment = scriptFile.filename

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'Update projects.items_attachment set ATTACHMENT = %s, att_size = %s where id =%s', (attachment, file_size, id))
    con.commit()
    # rows = cur.fetchall()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItemAttachmentDocs(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateItemsStatus/<status>/<id>', methods=['PUT'])
def update_items_status(status, id):
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select STATUS,user_id,project from projects.items where id ='+str(id))
    rows = cur.fetchall()
    previous_status = rows[0][0]
    user_id = rows[0][1]
    projects = rows[0][2]
    cur.execute(
        'UPDATE projects.items SET status = %s WHERE id = %s', (status, id))
    if int(status) == 6:
        cur.execute(
            'UPDATE projects.items SET date_close = %s WHERE id = %s', (now, id))
        cur.execute(
            'UPDATE projects.projects SET last_closed_date = %s WHERE id = %s', (now, projects))
    elif int(status) == 3:
        cur.execute(
            'UPDATE projects.items SET inprogress_date = %s WHERE id = %s', (now, id))
    elif int(status) == 5:
        cur.execute(
            'UPDATE projects.items SET completed_date = %s WHERE id = %s', (now, id))
    # else:
    #     cur.execute(
    #         'UPDATE projects.items SET date_close = %s WHERE id = %s', ('', id))

    if status != previous_status:
        cur.execute('Insert into projects.ITEMS_Comment_status (items_id, status, date, user_id) values(%s,%s,%s,%s)',
                    (id, status, now, user_id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemsPdf', methods=['POST'])
def get_item_pdf_all():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            html += """<td>""" + str(row[item]) + """</td>"""
        html += """</tr>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "item/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "item/pdf").mkdir(parents=True, exist_ok=True)

    html = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 25%
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center; color: gray;">Items</h1>
        <br>
        <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html+"""
    </table>
    </body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER']+"item/html/items.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"item/pdf/items.pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemWisePdf/<id>/<name>', methods=['GET'])
def get_itemWise_pdf(id, name):
    content = request.get_json(silent=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "item/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "item/pdf").mkdir(parents=True, exist_ok=True)

    finalResponse = []
    finalResponse1 = []
    finalResponse2 = []
    collectionName = None
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.users u on u.id  = tagtype) ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where projects.items.id ="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse2.append(columnValue)

    collectionHtml = """ """

    for items in finalResponse2:
        collectionName = str(items["item_id"])
        collectionHtml += """<tr class="collectionHtml">
                            <th>ID</th>
                            <td>"""+str(items["item_id"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Project</th>
                            <td>"""+str(items["project_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Date</th>
                            <td>"""+format_date(str(items["date"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Description</th>
                            <td>"""+str(items["description"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Priority</th>
                            <td>"""+str(items["priority_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Estimate</th>
                            <td>"""+str(items["estimate"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Actual</th>
                            <td>"""+str(items["actual"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Assignee</th>
                            <td>"""+str(items["assigneevalue"])[1:-1].replace("'", "")+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Collection</th>
                            <td>"""+str(items["collection_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Status</th>
                            <td>"""+str(items["status_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Title</th>
                            <td>"""+str(items["title"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Topic</th>
                            <td>"""+str(items["topic"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Follow-up</th>
                            <td>"""+str(items["followup"])+"""</td>
                        </tr> """

    cur.execute(
        "SELECT * from projects.items_attachment  WHERE items_id ="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)

    commentHtml = """ """
    for items in finalResponse:
        attachment = ""
        imageUrl = None
        if str(items['attachment']) != "":
            file_name, file_extension = os.path.splitext(
                str(items['attachment']))
            if file_extension == ".png" or file_extension == ".jpg":
                # imageUrl = Production.host+"ai/api/v2/downloadAttachment/"+str(id)+"/"+str(items['attachment'])
                imageUrl = app.config['UPLOAD_FOLDER'] + \
                    "attachments/"+str(id)+"/"+str(items['attachment'])
                attachment = """<img src='"""+imageUrl+"""' width="250" height="120"></img>"""
            else:
                imageUrl = Production.host+"ai/api/v2/downloadAttachment/" + \
                    str(id)+"/"+str(items['attachment'])
                attachment = str(imageUrl)

        commentHtml += """<tr>
                            <td>"""+str(items['comment'])+"""</td>
                            <td>"""+attachment+"""</td>
                            <td>"""+str(items['date'])+"""</td>
                        </tr>"""

    html = """<!DOCTYPE html>
 <html>
 <head>
    <meta http-equiv='cache-control' content='no-cache'>
    <meta http-equiv='expires' content='0'>
    <meta http-equiv='pragma' content='no-cache'>
    <meta http-equiv='Content-type' content='text/html; charset=utf-8' />
 	<style>
 		table {
 			font-family: arial, sans-serif;
 			border-collapse: collapse;
 			width: 100%;
 		}

 		td, th {
 			border: 1px solid #dddddd;
 			text-align: left;
 			padding: 8px;
 		}

 		.tableCollection{
 			width:80%;margin-left: auto;margin-right: auto;
 		}
        .collectionHtml th{
                background: #ddeaef;
                color: gray;
                width: 25%
        }
 	</style>
 </head>
 <body>
 	<h1 style="text-align: center; color:gray">"""+collectionName+"""</h1>
     <br>
 	<table class="tableCollection">
 		"""+collectionHtml+"""
 	</table>
     <br>
 	<br>
 	<h2 style="color:gray;">Comments/Attachment</h2>
 	<table>
 		<tr class="collectionHtml">
 			<th>Comment</th>
 			<th>Attachment</th>
 			<th>Date</th>
 		</tr>
 		"""+commentHtml+"""
 	</table>
 </body>
 </html>
"""
    # app.logger.info("attachment ==> %s",html)

    filepath = r''+app.config['UPLOAD_FOLDER']+"item/html/item1.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"item/pdf/item1.pdf"
    with open(filepath, mode="w", encoding="utf-8") as file:
        file.write(html)
    now = datetime.now()
    options = {
        "enable-local-file-access": "",
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape',
    }
    pdfkit.from_file(filepath, filepath1, options=options)
    con.close()
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"item/pdf/", filename="item1.pdf")


@endpointV2.route('/v2/getItemNotes/<itemId>', methods=['GET'])
def get_items_notes(itemId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.items_notes.*,PROJECTS.USERS.username FROM projects.items_notes left join PROJECTS.ITEMS on PROJECTS.ITEMS.id = projects.items_notes.ITEMS_ID left join PROJECTS.USERS on PROJECTS.USERS.id = PROJECTS.ITEMS.user_id   WHERE ITEMS_ID ="+itemId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setItemNote/<itemId>', methods=['POST'])
def set_item_note(itemId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('INSERT INTO projects.items_notes (ITEMS_ID,NOTE, DATE) VALUES (%s, %s, %s)',
                (itemId, content.get('note'), now.strftime("%m-%d-%Y %I:%M %p")))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getLastItemNotes/<itemId>', methods=['GET'])
def get_items_notes_last(itemId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.items_notes.*,PROJECTS.USERS.username FROM projects.items_notes left join PROJECTS.ITEMS on PROJECTS.ITEMS.id = projects.items_notes.ITEMS_ID left join PROJECTS.USERS on PROJECTS.USERS.id = PROJECTS.ITEMS.user_id   WHERE ITEMS_ID ="+itemId+" order by id desc limit 1;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateProfileImage/<username>', methods=['POST'])
def update_profile_image(username):
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"profile/" +
             username+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"profile/"+username+"/", scriptFile.filename))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"profile/"+username+"/", scriptFile.filename), "profile/"+username+"/"+scriptFile.filename)
        attachment = scriptFile.filename
    else:
        attachment = ""

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if(attachment == ""):
        cur.execute("update projects.users set name= %s WHERE username =%s",
                    (content.get("name"), username))
    else:
        cur.execute("update projects.users set name= %s, profile_image=%s WHERE username =%s",
                    (content.get("name"), attachment, username))
    con.commit()
    # rows = cur.fetchall()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getProfileImage/<fileName>/<username>', methods=['GET'])
def get_profile(fileName, username):

    if fileName is None or fileName == 'undefined':
        return ""

    mimeType = mimetypes.MimeTypes().guess_type(fileName)[0]
    signedFileURL = S3Client.create_presigned_url(
        "profile/"+username+"/"+fileName)
    app.logger.info("AWS S3 PreSigned URL:: %s, :: %s",
                    fileName, signedFileURL)
    s3FileObj = S3Client.get_object("profile/"+username+"/"+fileName)

    # return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"profile/"+username+"/", filename=fileName)

    return Response(s3FileObj['Body'].read(), content_type=mimeType)


@endpointV2.route('/v2/updateItemCollection/<collection>/<id>', methods=['PUT'])
def update_items_collection(collection, id):
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select assign_count from projects.items where id = '"+str(id)+"'")
    rows = cur.fetchall()
    count = rows[0][0]
    if count == None:
        count = 0
    count = int(count)+1
    cur.execute('UPDATE projects.items SET collection = %s, assign_count=%s WHERE id = %s',
                (collection, str(count), id))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/saveGitDetail/<projectId>', methods=['POST'])
def save_git_detail(projectId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('Insert into projects.git_details (project, owner_name, repo_name, userid, token) values(%s,%s,%s,%s,%s)',
                (projectId, content.get('owner'), content.get('repoName'), content.get('userId'), content.get('token')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getGitDetails/<projectId>', methods=['GET'])
def get_git_details(projectId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.git_details where project = "+projectId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateGitDetail/<projectId>', methods=['PUT'])
def update_git_detail(projectId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.git_details set owner_name = %s, repo_name = %s, userid= %s, token = %s where project = %s',
                (content.get('owner'), content.get('repoName'), content.get('userId'), content.get('token'), projectId))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCommitList', methods=['POST'])
def getCommitList():
    content = request.get_json(silent=True)
    finalResponse = []
    url = "https://"+content.get('userId')+":"+content.get(
        'token')+"@api.github.com/repos/"+content.get('owner')+"/"+content.get('repo')+"/commits"
    headers = {"Accept": "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=50)
    app.logger.info("response.status_code ==> %s", response.status_code)
    result = json.loads(response.text)
    return Response(response=dumps(result, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/testConnectionGit', methods=['POST'])
def testConnection():
    content = request.get_json(silent=True)
    finalResponse = []
    url = "https://"+content.get('userId')+":"+content.get(
        'token')+"@api.github.com/repos/"+content.get('owner')+"/"+content.get('repo')+"/commits"
    app.logger.info("response.status_code url ==> %s", url)
    headers = {"Accept": "application/vnd.github.v3+json"}
    response = requests.get(url, headers=headers, timeout=50)
    return jsonify({'code': "200", 'message': "success", 'status': response.status_code})


@endpointV2.route('/v2/getCollectionFilterGrid/<typeid>/<sortType>/<id>', methods=['GET'])
def get_collections_filterGrid(typeid, sortType, id):

    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = " where projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
            id)+") or projects.collections.projects && Array"+str(projectArr)
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = " where projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)+") or projects.collections.projects && Array"+str(projectUserList)
        elif userType == "I" and pInvite == False:
            query = " where projects.collections.projects && Array(select id from projects.projects where created_by = "+str(
                id)
        else:
            query = ""

    if sortType == "1":
        sType = "order by projects.collections.last_activity desc Nulls last"
    if sortType == "2":
        sType = "order by projects.collections.collection"
    if sortType == "3":
        sType = "order by projects.collection_sort.order_no Nulls last"

    if typeid == "1":
        sId = " "
    else:
        if query == "":
            sId = " where projects.collections.status ="+str(typeid)+" "
        else:
            sId = " and projects.collections.status ="+str(typeid)+" "

    # if query == "":
      ##      csId = " where projects.collection_sort.user_id ="+str(id)+" "
    # else:
      ##  csId = " and projects.collection_sort.user_id ="+str(id)+" "
    cur.execute("select projects.collections.*, (select sum(actual::numeric) from projects.items where actual != '' and actual is not null and collection = projects.collections.id) as actual_items, (select sum(estimate::numeric) from projects.items where estimate != '' and estimate is not null and collection = projects.collections.id) as estimated_items, (select count(*) from projects.items where status = 1 and collection = projects.collections.id) as open_items, (select count(*) from projects.items where status = 7 and collection = projects.collections.id) as qa, (select count(*) from projects.items where status != 6 and projects.items.status != 1 and collection = projects.collections.id) as progress_items, (select count(*) from projects.items where status = 6 and collection = projects.collections.id) as completed_items, projects.collection_status.name as status_name, (SELECT array_agg(t.team) filter(where u.team is not null) as teams FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project left join projects.teams t on t.id = Any(u.team) ), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id left join projects.collection_sort on projects.collections.id=projects.collection_sort.collection_id and projects.collection_sort.user_id ="+str(id)+query+" "+sId+sType)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionImage/<fileName>', methods=['GET'])
def get_collection_image(fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"collections/", filename=fileName)


@endpointV2.route('/v2/deleteGitDetail/<projectId>', methods=['GET'])
def delete_git_detail(projectId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'delete from projects.git_details where project ='+str(projectId))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/collectionExist/<collectionName>', methods=['GET'])
def collectionExist(collectionName):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select count(*) from projects.collections where LOWER(collection) = LOWER('"+collectionName+"')")
    status = True
    rows = cur.fetchall()
    if rows[0][0] == 0:
        status = False
    con.close()
    return jsonify({'code': "200", 'message': "success", 'status': status})


@endpointV2.route('/v2/projectExist/<projectName>', methods=['GET'])
def projectExist(projectName):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select count(*) from projects.projects where LOWER(project_name) = LOWER('"+projectName+"')")
    status = True
    rows = cur.fetchall()
    if rows[0][0] == 0:
        status = False
    con.close()
    return jsonify({'code': "200", 'message': "success", 'status': status})


@endpointV2.route('/v2/checkUserEmailAvailablity/<email>', methods=['GET'])
def checkUserEmailAvailablity(email):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select id from projects.users where username ='"+email+"'")
    rows = cur.fetchall()
    exist = None
    if len(rows) > 0:
        exist = True
    else:
        exist = False
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/getCollectionItems/<id>/<name>', methods=['GET'])
def getCollectionItems(id, name):
    html = """ """
    finalResponse1 = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.items.* ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where projects.items.collection ="+str(id)+" order by projects.items.item_id")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse1.append(columnValue)

    for items in finalResponse1:
        html += """<tr>
                    <td>"""+str(items['item_id'])+"""</td>
                    <td>"""+str(items['project_name'])+"""</td>
                    <td>"""+format_date(str(items['date']))+"""</td>
                    <td>"""+str(items['description'])+"""</td>
                    <td>"""+str(items['priority_name'])+"""</td>
                    <td>"""+str(items['estimate'])+"""</td>
                    <td>"""+str(items['actual'])+"""</td>
                    <td>"""+str(items['assignee'])+"""</td>
                    <td>"""+str(items['status_name'])+"""</td>
                    <td>"""+str(items['type_name'])+"""</td>
                </tr>"""

    # for i,row in enumerate(content.get('rowData')):
    #     html += """<tr>"""
    #     for item in columnValue:
    #         html += """<td>""" +str(row[item]) + """</td>"""
    #     html += """</tr>"""

    html_str = """<head>
    <meta http-equiv="pragma" content="no-cache" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.10.21/css/jquery.dataTables.css">
 <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/buttons/1.6.2/css/buttons.dataTables.min.css">
  <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
</head>
    <h2 style="text-align:center">"""+name + """</h2></div><br>
    <table id="table_id" class="display">
    <thead>
        <tr>
            <th>ID</th>
 			<th>Project</th>
            <th>Date</th>
 			<th>Description</th>
 			<th>Priority</th>
 			<th>Estimate</th>
 			<th>Actual</th>
 			<th>Assignee</th>
 			<th>Status</th>
 			<th>Type</th>
        </tr>
        <thead>
        <tbody>""" + html + """<tbody></table>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/1.10.21/js/jquery.dataTables.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/dataTables.buttons.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.flash.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/pdfmake.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/pdfmake/0.1.53/vfs_fonts.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.3/jszip.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.html5.min.js"></script>
        <script type="text/javascript" charset="utf8" src="https://cdn.datatables.net/buttons/1.6.2/js/buttons.print.min.js"></script>
        <script type="text/javascript">$(document).ready( function () {
    $('#table_id').DataTable({
        dom: 'Blfrtip',
        buttons: [
            {
                extend: 'excel',
                title: '"""+name + """'
            },
            {
                extend: 'pdf',
                title: '"""+name + """',
                orientation : 'landscape',
                pageSize : 'LEGAL',
            }
        ]
    });
} );</script>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "collection/html/").mkdir(parents=True, exist_ok=True)

    filepath = r''+app.config['UPLOAD_FOLDER']+"collection/html/"+name+".html"
    with open(filepath, "w") as file:
        file.write(html_str)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/forgotPassword/<email>', methods=['GET'])
def forgotPassword(email):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select id, name from projects.users where username = '"+email+"'")
    rows = cur.fetchall()
    id = rows[0][0]
    name = rows[0][1]
    msg = Message(
        "Update Password for Istoria",
        sender=('Istoria Team', mailSender),
        recipients=[email]
    )
    random = get_random_string(12)
    hash1 = sha256(random.encode()).hexdigest()
    cur.execute(
        'INSERT INTO PROJECTS.forgot_password_hash (user_id, hash_code) values (%s,%s)', (id, hash1))
    con.commit()
    body = "Dear " + name+",\nYou requested for the password update of your istoria account.\nPlease click on the link below to update password:\n\n" + \
        Production.host+"forgotPassword?id=" + \
        str(hash1)+"\n\nHave a wonderful day!\n\nThank you,\nIstoria Team"
    msg.body = body
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getHashId/<hash>', methods=['GET'])
def getHashId(hash):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select user_id from PROJECTS.forgot_password_hash where hash_code ='"+str(hash)+"'")
    rows = cur.fetchall()
    if len(rows) < 1:
        resp = False
        id = ""
    else:
        resp = True
        id = rows[0][0]
    con.close()
    return jsonify({'code': "200", 'message': "success", "id": id, "resp": resp})


@endpointV2.route('/v2/removeHashId/<id>', methods=['GET'])
def removeHashId(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("delete from PROJECTS.forgot_password_hash where user_id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/changePassword/<id>', methods=['POST'])
def update_password(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    hased_password = generate_password_hash(
        content.get('password'), method='sha256')
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "update projects.users set password= %s WHERE id = %s", (hased_password, id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "Success"})


@endpointV2.route('/v2/scriptUpload', methods=['POST'])
def script_upload():
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"upload/" +
             content.get("userId")+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"upload/"+content.get("userId")+"/", scriptFile.filename.lower()))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"upload/"+content.get("userId")+"/", scriptFile.filename.lower()), "upload/"+content.get("userId")+"/"+scriptFile.filename.lower())
        attachment = scriptFile.filename

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()

    json_object = json.dumps(content.get('data'), indent=4)
    cur.execute("Insert into PROJECTS.upload_file (project_id, user_id, description, date, file_type, file_name, upload_type) values (%s,%s,%s,%s,%s,%s,%s) returning id",
                (content.get("project"), content.get("userId"), content.get("file_description"), now, content.get("file_type"), attachment, content.get("upload_type")))
    rows = cur.fetchall()
    retun_id = rows[0][0]
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success", "id": retun_id})


@endpointV2.route('/v2/getCatalogFiles/<userId>', methods=['GET'])
def get_all_files(userId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.upload_file.*, projects.projects.project_name, projects.users.name from projects.upload_file left join projects.projects on projects.upload_file.project_id = projects.projects.id left join projects.users on projects.upload_file.user_id =  projects.users.id where user_id = "+userId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteFile/<id>', methods=['DELETE'])
def delete_file(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("delete from PROJECTS.upload_file where id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getMessageConfig/<id>', methods=['GET'])
def get_message_file(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.stream.user_id="+str(id)+" or projects.stream.user_id="+str(
            inviteUserId)+" and projects.stream.project_id && Array"+str(projectArr)
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.stream.user_id =" + \
                str(id)+" or projects.stream.project_id && Array" + \
                str(projectUserList)
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.stream.user_id ="+str(id)
        else:
            query = ""

    cur.execute("select PROJECTS.stream.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.stream.project_id) project LEFT JOIN projects.projects u on u.id = project), projects.users.name from PROJECTS.stream  left join projects.users on PROJECTS.stream.user_id = projects.users.id "+query + " order by id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/saveStream/<projectId>/<userId>', methods=['POST'])
def save_stream(projectId, userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if content.get('type') == "I":
        cur.execute('select item_id from projects.items where id =' +
                    str(content.get('id')))
        rows = cur.fetchall()
        ref = rows[0][0]
        ref_type = content.get('type')
        ref_id = content.get('id')
    elif content.get('type') == "P":
        cur.execute(
            'select project_name from projects.projects where id ='+str(content.get('id')))
        rows = cur.fetchall()
        ref = rows[0][0]
        ref_type = content.get('type')
        ref_id = content.get('id')
    elif content.get('type') == "C":
        cur.execute(
            'select collection from projects.collections where id ='+str(content.get('id')))
        rows = cur.fetchall()
        ref = rows[0][0]
        ref_type = content.get('type')
        ref_id = content.get('id')

    li = []
    li.append(int(projectId))
    cur.execute('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information,activity_id, reference_id,reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (li, userId, content.get('activity'), ref, now, now.strftime("%I:%M %p"), content.get('information'), content.get('a_id'), ref_id, ref_type, content.get('action')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getStreamActivity', methods=['GET'])
def getStreamActivity():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT * FROM projects.stream_activity ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/changeStreamActivity/<id>/<filterId>/<filterType>', methods=['GET'])
def changeStreamActivity(id, filterId, filterType):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if filterType == "N":
        subFilter = ""
    else:
        subFilter = " and projects.stream.reference_type = '" + \
            str(filterType)+"'"

    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.stream.user_id="+str(id)+" or projects.stream.user_id="+str(
            inviteUserId)+" and projects.stream.project_id = ANY(Array"+str(projectArr)+") and projects.stream.activity_id = "+str(filterId)+subFilter
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.stream.user_id ="+str(id)+" or projects.stream.project_id && Array"+str(
                projectUserList)+" and projects.stream.activity_id = "+str(filterId)+subFilter
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.stream.user_id =" + \
                str(id) + " and projects.stream.activity_id = " + \
                str(filterId)+subFilter
        else:
            query = " where projects.stream.activity_id = " + \
                str(filterId)+subFilter

    cur.execute("select PROJECTS.stream.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.stream.project_id) project LEFT JOIN projects.projects u on u.id = project), projects.users.name from PROJECTS.stream  left join projects.users on PROJECTS.stream.user_id = projects.users.id "+query + " order by id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/saveStreamCollection/<userId>', methods=['POST'])
def save_stream_collection(userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    if content.get('type') == "C":
        cur.execute(
            'select collection, projects from projects.collections where id ='+str(content.get('id')))
        rows = cur.fetchall()
        ref = rows[0][0]
        projects = rows[0][1]

    li = []
    for i in projects:
        li.append(int(i))

    cur.execute('Insert into projects.stream (project_id,user_id, activity, reference, date, time, information,activity_id, reference_id,reference_type,action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (li, userId, content.get('activity'), ref, now, now.strftime("%I:%M %p"), content.get('information'), content.get('a_id'), content.get('id'), content.get('type'), content.get('action')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getMessageConfigForItems/<id>/<itemId>', methods=['GET'])
def get_message_for_items(id, itemId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.stream.user_id="+str(id)+" or projects.stream.user_id="+str(inviteUserId)+" and projects.stream.project_id = ANY(Array"+str(
            projectArr)+") and projects.stream.reference_type = 'I' and projects.stream.reference_id = "+str(itemId)
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.stream.user_id ="+str(id)+" or projects.stream.project_id && Array"+str(
                projectUserList)+" and projects.stream.reference_type = 'I' and projects.stream.reference_id = "+str(itemId)
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.stream.user_id =" + \
                str(id) + " and projects.stream.reference_type = 'I' and projects.stream.reference_id = "+str(itemId)
        else:
            query = " where projects.stream.reference_type = 'I' and projects.stream.reference_id = " + \
                str(itemId)

    cur.execute("select PROJECTS.stream.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.stream.project_id) project LEFT JOIN projects.projects u on u.id = project), projects.users.name from PROJECTS.stream  left join projects.users on PROJECTS.stream.user_id = projects.users.id "+query + " order by id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getStreamPdf', methods=['POST'])
def getStreamPdf():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            if row[item] is not None:
                html += """<td>""" + \
                    listToStringWithoutBrackets(str(row[item])) + """</td>"""
        html += """</tr>"""

    Path(app.config['UPLOAD_FOLDER']+name +
         "/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER']+name +
         "/pdf").mkdir(parents=True, exist_ok=True)

    html = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 1%;
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center; color: gray;">"""+name.upper()+"""</h1>
        <br>
        <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html+"""
    </table>
    </body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER']+name+"/html/"+name+".html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+name+"/pdf/"+name+".pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/downloadStreamItems/<stream>', methods=['GET'])
def downloadStreamItems(stream):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"stream/pdf/", filename="stream.pdf")


@endpointV2.route('/v2/getItemStatusName/<id>/<id1>', methods=['GET'])
def getItemStatusName(id, id1):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    query = ""
    if int(id) > int(id1):
        query = " order by id desc"
    cur.execute("select * from projects.status where id = " +
                str(id)+" or id ="+str(id1) + query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionName/<id>/<id1>', methods=['GET'])
def getCollectionName(id, id1):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    query = ""
    app.logger.info("getCollectionName ==> %s,  %s", id, id1)
    if int(id) > int(id1):
        query = " order by id desc"
    cur.execute(" select collection from projects.collections where id = " +
                str(id)+" or id ="+str(id1)+query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionStatusName/<id>/<id1>', methods=['GET'])
def getCollectionStatusName(id, id1):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    query = ""
    if int(id) > int(id1):
        query = " order by id desc"
    cur.execute("select * from projects.collection_status where id = " +
                str(id)+" or id ="+str(id1) + query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTaggedPdf', methods=['POST'])
def getTaggedPdf():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            app.logger.info("item ==>> %s", item)
            if item == "date" or item == "tag_date":
                html += """<td>""" + format_date(str(row[item])) + """</td>"""
            else:
                html += """<td>""" + \
                    listToStringWithoutBrackets(str(row[item])) + """</td>"""
        html += """</tr>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "tag/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "tag/pdf").mkdir(parents=True, exist_ok=True)

    html = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 6%;
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center;color: gray;">Tagged</h1>
        <br>
        <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html+"""
    </table>
    </body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER']+"tag/html/tag.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"tag/pdf/tag.pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/downloadTagItems/<tag>', methods=['GET'])
def downloadTagItems(tag):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"tag/pdf/", filename="tag.pdf")


@endpointV2.route('/v2/getProjectPdf', methods=['POST'])
def getProjectPdf():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            if item == "last_item" and row[item] != None:
                html += """<td>""" + format_date(str(row[item])) + """</td>"""
            else:
                html += """<td>""" + \
                    listToStringWithoutBrackets(str(row[item])) + """</td>"""
        html += """</tr>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "project/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "project/pdf").mkdir(parents=True, exist_ok=True)

    html = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 1%;
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center;color: gray;">Projects</h1>
        <br>
        <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html+"""
    </table>
    </body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER']+"project/html/project.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"project/pdf/project.pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/downloadProjectPdf/<project>', methods=['GET'])
def downloadProjectPdf(project):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"project/pdf/", filename="project.pdf")


@endpointV2.route('/v2/getCollectionNameById/<id>', methods=['GET'])
def getCollectionNameById(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select collection from projects.collections where id = "+str(id))
    rows = cur.fetchall()
    name = rows[0][0]
    con.close()
    return jsonify({'code': "200", 'message': "success", "name": name})


@endpointV2.route('/v2/filterStreamByDate/<id>/<fromD>/<to>', methods=['GET'])
def filterStreamByDate(id, fromD, to):
    dateF = " projects.stream.date between '"+fromD+"' and '"+to+"'"
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.stream.user_id="+str(id)+" or projects.stream.user_id="+str(
            inviteUserId)+" and projects.stream.project_id = ANY(Array"+str(projectArr)+") and "+dateF
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.stream.user_id =" + \
                str(id)+" or projects.stream.project_id && Array" + \
                str(projectUserList)+" and "+dateF
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.stream.user_id ="+str(id)+" and"+dateF
        else:
            query = " where "+dateF

    cur.execute("select PROJECTS.stream.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.stream.project_id) project LEFT JOIN projects.projects u on u.id = project), projects.users.name from PROJECTS.stream  left join projects.users on PROJECTS.stream.user_id = projects.users.id "+query + " order by id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getDataPdf', methods=['POST'])
def getDataPdf():
    columnValue = []
    content = request.get_json(silent=True)
    columnList = content.get('columnDef')
    name = content.get('name')
    columnHtml = """ """
    for item in columnList:
        columnHtml += """<th>"""+item['columnDisplayName']+"""</th>"""
        columnValue.append(item['tableColumnName'])

    html = """ """
    for i, row in enumerate(content.get('rowData')):
        html += """<tr>"""
        for item in columnValue:
            if row[item] is not None:
                html += """<td>""" + \
                    listToStringWithoutBrackets(str(row[item])) + """</td>"""
        html += """</tr>"""

    Path(app.config['UPLOAD_FOLDER'] +
         "data/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "data/pdf").mkdir(parents=True, exist_ok=True)

    html = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 1%;
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center;color: gray;">"""+name.upper()+"""</h1>
        <br>
        <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html+"""
    </table>
    </body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER']+"data/html/"+name+".html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"data/pdf/"+name+".pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/downloadDataPdf/<name>', methods=['GET'])
def downloadDataPdf(name):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"data/pdf/", filename=name+".pdf")


@endpointV2.route('/v2/getCollectionIdByName/<name>', methods=['GET'])
def getCollectionIdByName(name):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select id from projects.collections where collection = '"+str(name)+"'")
    rows = cur.fetchall()
    id = rows[0][0]
    con.close()
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/deleteItemTagByItemId/<id>/<userId>', methods=['GET'])
def deleteItemTagByItemId(id, userId):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "DELETE FROM projects.item_tag WHERE item_id = %s and user_id=%s", (id, userId))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getNameById/<typeName>/<id>', methods=['GET'])
def getNameById(typeName, id):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects."+str(typeName)+" where id = "+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllPages/<userId>', methods=['GET'])
def getCreatedPage(userId):
    finalResponse = []
    content = request.get_json(silent=True)

    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+userId)
    if rows is not None and len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE (cp.user_id="+str(id)+" or cp.user_id="+str(inviteUserId) + \
            " and cp.projects && (Array"+str(projectArr) + \
            ")) or cp.page_type = 'Public'"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+userId)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE (cp.user_id ="+str(userId)+" or cp.projects && (Array" + \
                str(projectUserList)+")) or cp.page_type = 'Public'"
        elif userType == "I" and pInvite == False:
            query = "WHERE cp.user_id =" + \
                str(userId) + " or cp.page_type = 'Public'"
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select cp.*,projects.users.name as username, (SELECT array_agg(u.color) as color FROM unnest(cp.tags) tagType LEFT JOIN projects.pageTagType u on u.id = tagType), (SELECT array_agg(u.title) as tagTitle FROM unnest(cp.tags) tagType LEFT JOIN projects.pageTagType u on u.id = tagType), (SELECT array_agg(u.project_name) as project_name FROM unnest(cp.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.created_page cp left join projects.users on projects.users.id = cp.user_id "+str(query) + "  order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


def random_with_N_digits(n):
    range_start = 10**(n-1)
    range_end = (10**n)-1
    return randint(range_start, range_end)


@endpointV2.route('/v2/deletePage/<id>', methods=['GET'])
def deletePage(id):
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM PROJECTS.created_page WHERE id = '" + id + "'")
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


def hasNumbers(inputString):
    return any(char.isdigit() for char in inputString)


@endpointV2.route('/v2/clonePage/<userId>', methods=['POST'])
def clonePage(userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    if hasNumbers(content.get('url')) and "copy" in content.get('url'):
        number = re.findall("\d+", content.get('url'))
        nl = len(number)-1
        number = int(number[nl])
        app.logger.info("clonePage ==> %s, -->  %s",
                        content.get('url'), content.get('url')[:-11])
        finalUrl = content.get('url')[:-11] + " ( copy-"+str(number+1)+" )"
        finalPageId = content.get(
            'pageId')[:-11] + " ( copy "+str(number+1)+" )"

    else:
        finalUrl = content.get('url')+" ( copy-1 )"
        finalPageId = content.get('pageId')+" ( copy 1 )"

    finalUrl1 = finalUrl.replace("'", "''")
    rows = SQLHelpers.getInstance().executeRawResult(
        "select * from projects.created_page where lower(url) = lower('"+finalUrl1+"') and user_id = "+str(userId))

    toggle = False
    # app.logger.info("finalUrl ==> %s",len(rows))
    if len(rows) == 0:
        rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.created_page (user_id, title,file_name, created_on, status, url, pageid, projectinfo, projects) values(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                                                      (userId, content.get('title'), content.get('fileName'), now.strftime("%m-%d-%Y"), "Pending", finalUrl, finalPageId, content.get('projectInfo'), content.get('projects')))
        toggle = True

    return jsonify({'code': "200", 'message': "success", "toggle": toggle})


@endpointV2.route('/v2/changePageStatus/<id>', methods=['POST'])
def changePageStatus(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("update PROJECTS.created_page set status = %s WHERE id = %s",
                (content.get('status'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "Success"})


@endpointV2.route('/v2/getJsonFile/<userId>/<id>/<rId>', methods=['GET'])
def getJsonFile(userId, id, rId):
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select file_name FROM PROJECTS.created_page WHERE id = '" + id + "'")
    rows = cur.fetchall()
    fileName = "Page-"+str(rows[0][0])
    con.close()
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"pages/"+userId+"/", filename=fileName+".json")


@endpointV2.route('/v2/getPageDetailById/<id>', methods=['GET'])
def getPageTitle(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * FROM PROJECTS.created_page WHERE id = '" + id + "'")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updatePage/<userId>/<id>', methods=['POST'])
def updatePage(userId, id):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    json_object = json.dumps(content.get('data'), indent=4)
    json_object1 = json.dumps(content.get('rectangles'), indent=4)
    # cur.execute("select file_name FROM PROJECTS.created_page WHERE id = '" + id +"'")
    random = str(random_with_N_digits(6))
    name = "Page-" + str(random)
    rect = "Rect-" + str(random)
    Path(app.config['UPLOAD_FOLDER']+"pages/" +
         userId+"/").mkdir(parents=True, exist_ok=True)
    filepath = r''+app.config['UPLOAD_FOLDER']+"pages/"+userId+"/"+name+".json"
    filepath1 = r''+app.config['UPLOAD_FOLDER'] + \
        "pages/"+userId+"/"+rect+".json"

    with open(filepath, "w") as outfile:
        outfile.write(json_object)
    with open(filepath1, "w") as outfile:
        outfile.write(json_object1)
    cur.execute('update PROJECTS.created_page set file_name=%s, tags=%s  where id = %s',
                (random, content.get('tags'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getRectFile/<userId>/<id>/<rId>', methods=['GET'])
def getRectFile(userId, id, rId):
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select file_name FROM PROJECTS.created_page WHERE id = '" + id + "'")
    rows = cur.fetchall()
    fileName = "Rect-"+str(rows[0][0])
    con.close()
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"pages/"+userId+"/", filename=fileName+".json")


@endpointV2.route('/v2/sendPageEmailLink/<id>', methods=['POST'])
def sendPageEmailLink(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select name from projects.users where id ="+str(id))
    rows = cur.fetchall()
    name = rows[0][0]
    msg = Message(
        "Page Link for Istoria",
        sender=('Istoria Team', mailSender),
        recipients=[content.get("email")]
    )
    con.commit()
    body = "Dear user,\n"+str(name)+" shared a page link with you.\n"+str(
        content.get("link"))+" \n\nHave a wonderful day!\n\nThank you,\nIstoria Team"
    msg.body = body
    mail.send(msg)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemByName/<id>', methods=['GET'])
def getItemByName(id):
    finalResponse = []
    content = request.get_json(silent=True)
    finalResponse = SQLHelpers.getInstance().executeQuery("SELECT it.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(it.assignee) tagType LEFT JOIN projects.users u on u.id  = tagtype), p.project_name, cl.collection  as collection_name FROM projects.items it left join projects.collections cl on cl.id=it.collection left join projects.projects p on p.id=it.project WHERE LOWER(it.item_id) = LOWER('"+str(id)+"')")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectByName', methods=['GET'])
def getProjectByName():
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT id, project_name FROM projects.projects order by id ")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/pageTitleExist/<url>/<userId>', methods=['GET'])
def pageTitleExist(url, userId):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "select * from projects.created_page where title = %s or url = %s and user_id = %s", (url, url, userId))
    rows = cur.fetchall()
    toggle = False
    if len(rows) > 0:
        toggle = True
    con.close()
    return jsonify({'code': "200", 'message': "success", "exist": toggle})


@endpointV2.route('/v2/getIdByName/<pageName>/<username>', methods=['GET'])
def getIdByName(pageName, username):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select id, user_id from PROJECTS.created_page where title = %s or url = %s and user_id = (select id from projects.users where username = %s) ;", (pageName, pageName, username))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/savePageStream/<userId>', methods=['POST'])
def savePageStream(userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('Insert into projects.stream (user_id, date, time, activity_id,action, information) values(%s,%s,%s,%s,%s,%s)', (userId,
                                                                                                                                 now.strftime("%m-%d-%Y"), now.strftime("%I:%M %p"), content.get('a_id'), content.get('action'), content.get('information')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/tagTypeSave/<userID>', methods=['POST'])
def tagTypeSave(userID):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('Insert into PROJECTS.tagType (user_id,title, color) values(%s,%s,%s)',
                (userID, content.get('title'), content.get('color')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getTagType/<userID>', methods=['GET'])
def getTagType(userID):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from PROJECTS.tagType where user_id ="+str(userID))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllTagsByTypeId/<userId>', methods=['POST'])
def getAllTagsByTypeId(userId):
    finalResponse = []
    content = request.get_json(silent=True)
    filterTags = content.get("filterTags")
    if(filterTags is not None and len(filterTags) > 0):
        finalResponse = SQLHelpers.getInstance().executeQuery("select PROJECTS.ITEM_TAG.id as tag_id,projects.projects.project_name,PROJECTS.ITEM_TAG.date as tag_date, projects.items.*,(SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype),PROJECTS.ITEM_TAG.user_id as userid ,projects.collections.collection as collection_name,PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from PROJECTS.ITEM_TAG left join projects.items on PROJECTS.ITEM_TAG.item_id = projects.items.id left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type on projects.items.type = PROJECTS.type.id left join projects.projects on projects.items.project = projects.projects.id left join projects.collections on projects.items.collection = projects.collections.id  where projects.item_tag.user_id ="+userId + " and (ARRAY"+str(filterTags)+" && projects.items.tagtype) ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateItemTagType/<id>', methods=['PUT'])
def updateItemTagType(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("UPDATE projects.items SET tagType=%s WHERE id = %s",
                (content.get("tagType"), str(id)))
    con.commit()
    con.close()
    try:
        idList = [id]
        if ES_SYNC_ON:
            indexItems(idList)
    except Exception as ex:
        pass
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/savePage/<userId>', methods=['POST'])
def savePage(userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.created_page (user_id, title, created_on, status, url, pageid, projectinfo, projects) values(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                                                  (userId, content.get('title'), now.strftime("%m-%d-%Y"), "Pending", content.get('url'), content.get('pageId'), content.get('projectInfo'), content.get('projects')))
    id = rows[0][0]
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/pageIdExist/<url>/<id>/<userId>', methods=['GET'])
def pageIdExist(url, id, userId):
    finalResponse = []
    url = url.replace("'", "''")
    id = id.replace("'", "''")
    app.logger.info("pageIdExist --> %s,%s", url, id)
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeRawResult(
        "select * from projects.created_page where lower(url) = lower('"+url+"') and user_id = "+str(userId))
    rows1 = SQLHelpers.getInstance().executeRawResult(
        "select * from projects.created_page where lower(pageid) = lower('"+id+"') and user_id = "+str(userId))

    toggle = False
    toggle1 = False
    if len(rows) > 0:
        toggle = True
    if len(rows1) > 0:
        toggle1 = True
    return jsonify({'code': "200", 'message': "success", "existUrl": toggle, "existId": toggle1})


@endpointV2.route('/v2/collectionCutomSort/<userId>', methods=['POST'])
def collectionCutomSort(userId):
    finalResponse = []
    content = request.get_json(silent=True)
    #app.logger.info("content --> %s,%s",userId,content)
    for key in content:
        collectionId = key.get('collectionId')
        orderNo = key.get('orderNo')
        rows = SQLHelpers.getInstance().executeRawResult(
            "select * from projects.collection_sort where collection_id  = "+str(collectionId)+" and user_id = "+str(userId))
        toggle = False
        if(rows != None and len(rows) > 0):
            toggle = True
        if(toggle):
            rows1 = SQLHelpers.getInstance().executeUpdate(
                'update projects.collection_sort set order_no=%s where user_id = %s and collection_id=%s', (orderNo, userId, collectionId))
        else:
            rows2 = SQLHelpers.getInstance().executeUpdate(
                'Insert into projects.collection_sort (user_id, collection_id , order_no) values(%s,%s,%s) RETURNING id', (userId, collectionId, orderNo))

    return jsonify({'code': "200", 'message': "success", "existUrl": True, "existId": True})


@endpointV2.route('/v2/downloadPageList/<name>', methods=['GET'])
def downloadPageList(name):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+name+"/pdf/", filename=name+".pdf")


@endpointV2.route('/v2/getLogs/<userId>/<id>', methods=['GET'])
def getLogs(userId, id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.logs where user_id ="+str(userId)+" and page_id="+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/saveLogs', methods=['POST'])
def saveLogs():
    content = request.get_json(silent=True)
    now = datetime.now()
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.logs (user_id, page_id, ip, location, browser, device, date_time) values(%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('userId'), content.get('pageId'), content.get('ip'), content.get('location'), content.get('browser'), content.get('device'), now.strftime("%m-%d-%Y %I:%M:%p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getPageFiltered/<userId>/<filterType>', methods=['GET'])
def getPageFiltered(userId, filterType):
    finalResponse = []
    content = request.get_json(silent=True)
    if(filterType == "Private"):
        rows = SQLHelpers.getInstance().executeRawResult(
            'select invite_by,project from projects.user_project_mapping where user_id ='+userId)
        if len(rows) > 0:
            inviteUserId = rows[0][0]
            projectArr = rows[0][1]
            query = "WHERE (cp.user_id="+str(id)+" or cp.user_id="+str(inviteUserId) + \
                " and cp.projects && (Array"+str(projectArr) + \
                ")) and cp.page_type = '"+str(filterType)+"'"
        else:
            rows = SQLHelpers.getInstance().executeRawResult(
                'select type, username from projects.users where id ='+userId)
            userType = rows[0][0]
            username = rows[0][1]
            rows = SQLHelpers.getInstance().executeRawResult(
                "select project from projects.invite where email ='"+username+"'")
            pInvite = False
            if len(rows) > 0:
                projectUserList = rows[0][0]
                pInvite = True
            if userType == "I" and pInvite == True:
                query = "WHERE (cp.user_id ="+str(userId)+" or cp.projects && (Array"+str(
                    projectUserList)+")) and cp.page_type = '"+str(filterType)+"'"
            # elif userType == "I" and pInvite == False:
            #     query = "WHERE cp.user_id ="+str(userId) +" and cp.page_type = "+str(filterType)
            else:
                query = "WHERE cp.user_id =" + \
                    str(userId) + " and cp.page_type = '"+str(filterType)+"'"

        finalResponse = SQLHelpers.getInstance().executeQuery("select cp.*,projects.users.name as username, (SELECT array_agg(u.project_name) as project_name FROM unnest(cp.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.created_page cp left join projects.users on projects.users.id = cp.user_id "+str(query) + "  order by id desc")
    else:
        query = "WHERE cp.page_type = '"+str(filterType)+"'"
        finalResponse = SQLHelpers.getInstance().executeQuery("select cp.*,projects.users.name as username, (SELECT array_agg(u.project_name) as project_name FROM unnest(cp.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.created_page cp left join projects.users on projects.users.id = cp.user_id "+str(query) + "  order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/pageTagTypeSave/<userID>', methods=['POST'])
def pageTagTypeSave(userID):
    content = request.get_json(silent=True)
    now = datetime.now()
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('Insert into PROJECTS.pageTagType (user_id,title, color) values(%s,%s,%s)',
                (userID, content.get('title'), content.get('color')))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getPagTagType/<userID>', methods=['GET'])
def getPagTagType(userID):
    finalResponse = []
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from PROJECTS.pageTagType where user_id ="+str(userID))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllPagesByTypeId/<userId>', methods=['POST'])
def getAllPagesByTypeId(userId):
    finalResponse = []
    content = request.get_json(silent=True)
    filterTags = content.get("filterTags")
    if(filterTags is not None and len(filterTags) > 0):
        finalResponse = SQLHelpers.getInstance().executeQuery("select cp.*,projects.users.name as username,(SELECT array_agg(u.color) as color FROM unnest(cp.tags) tagType LEFT JOIN projects.pageTagType u on u.id = tagType), (SELECT array_agg(u.title) as tagTitle FROM unnest(cp.tags) tagType LEFT JOIN projects.pageTagType u on u.id = tagType), (SELECT array_agg(u.project_name) as project_name FROM unnest(cp.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.created_page cp left join projects.users on projects.users.id = cp.user_id WHERE (ARRAY"+str(filterTags)+" && cp.tags) and (cp.user_id ="+str(userId) + " or cp.page_type = 'Public') order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updatePageTags/<id>', methods=['POST'])
def updatePageTags(id):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate(
        'update PROJECTS.created_page set tags=%s where id = %s', (content.get('tags'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getTeamList/<id>', methods=['GET'])
def getTeamList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.team_members.*,(SELECT array_agg(u.team) as team_name FROM unnest(projects.team_members.team) inst LEFT JOIN projects.teams u on u.id = inst), projects.users.username from projects.team_members left join projects.users on projects.team_members.created_by = projects.users.id where created_by ="+id + " order by projects.team_members.name")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getLicenseList/<id>', methods=['GET'])
def getLicenseList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select projects.licenses.*, projects.users.username from projects.licenses left join projects.users on projects.licenses.created_by = projects.users.id where created_by ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addTeamMembers/<userID>', methods=['POST'])
def addTeamMembers(userID):
    content = request.get_json(silent=True)
    email = content.get('email')
    rowId = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.team_members (name, title, team, email, mobile, phone, projects_info, info, location, reports_to, created_by) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id',
                                                   (content.get('name'), content.get('title'), content.get('team'), content.get('email'), content.get('mobile'), content.get('phone'), content.get('projectsInfo'), content.get('info'), content.get('location'), content.get('reports_to'), userID))
    rows = SQLHelpers.getInstance().executeRawResult(
        "select id from projects.users where lower(username)='"+str(email.lower())+"'")
    if len(rows) > 0:
        uId = rows[0][0]
        tmId = rowId[0][0]
        SQLHelpers.getInstance().executeUpdate(
            'Insert into PROJECTS.team_member_mapping (team_member_id, user_id) values(%s,%s)', (tmId, uId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCollectionPdf/<id>/<name>', methods=['GET'])
def get_collection_pdf(id, name):
    content = request.get_json(silent=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "collection/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "collection/pdf").mkdir(parents=True, exist_ok=True)

    finalResponse = []
    finalResponse1 = []
    finalResponse2 = []
    finalResponse3 = []
    collectionName = None
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.collections.*, (select count(*) from projects.items where status != 6 and collection = projects.collections.id) as open_items,(select count(*) from projects.items where collection = projects.collections.id) as items, projects.collection_status.name as status_name, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.collections.projects) project LEFT JOIN projects.projects u on u.id = project) from projects.collections left join projects.collection_status on projects.collections.status = projects.collection_status.id where projects.collections.id="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse2.append(columnValue)

    collectionHtml = """ """

    for items in finalResponse2:
        collectionName = str(items["collection"])
        collectionHtml += """<tr class="collectionHtml">
                            <th>Collection Id</th>
                            <td>"""+str(items["collection"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Goals/Description</th>
                            <td>"""+str(items["description"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Projects</th>
                            <td>"""+listToStringWithoutBrackets(str(items["project_name"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>From</th>
                            <td>"""+format_date(str(items["from_date"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>To</th>
                            <td>"""+format_date(str(items["to_date"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Status</th>
                            <td>"""+str(items["status_name"])+"""</td>
                        </tr> """

    cur.execute(
        "SELECT * from projects.collection_attachment  WHERE collection_id ="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)

    commentHtml = """ """
    for items in finalResponse:
        attachment = ""
        imageUrl = None
        if str(items['attachment']) != "":
            file_name, file_extension = os.path.splitext(
                str(items['attachment']))
            if file_extension == ".png" or file_extension == ".jpg":
                imageUrl = app.config['UPLOAD_FOLDER'] + \
                    "attachments/"+str(id)+"/"+str(items['attachment'])
                attachment = """<img src=" """+imageUrl+"""" width="250" height="120"></img>"""
            else:
                imageUrl = Production.host+"ai/api/v2/downloadAttachment/" + \
                    str(id)+"/"+str(items['attachment'])
                attachment = imageUrl

        commentHtml += """<tr>
                            <td>"""+str(items['comment'])+"""</td>
                            <td>"""+str(attachment)+"""</td>
                            <td>"""+str(items['date'])+"""</td>
                        </tr>"""

    cur.execute("SELECT projects.items_attachment.*,projects.items.item_id from projects.items_attachment left join projects.items on projects.items_attachment.items_id = projects.items.id  where items_id = ANY(Array(select array_agg(id::int) from projects.items where collection = "+str(id)+")) ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse3.append(columnValue)

    commentHtmlItems = """ """
    for items in finalResponse3:
        attachment = ""
        imageUrl = None
        if str(items['attachment']) != "":
            file_name, file_extension = os.path.splitext(
                str(items['attachment']))
            if file_extension == ".png" or file_extension == ".jpg":
                imageUrl = app.config['UPLOAD_FOLDER']+"attachments/" + \
                    str(items['items_id'])+"/"+str(items['attachment'])
                attachment = """<img src=" """+imageUrl+"""" width="250" height="120"></img>"""
            else:
                imageUrl = Production.host+"ai/api/v2/downloadAttachment/" + \
                    str(items['items_id'])+"/"+str(items['attachment'])
                attachment = imageUrl

        commentHtmlItems += """<tr>
                            <td>"""+str(items['item_id'])+"""</td>
                            <td>"""+str(items['comment'])+"""</td>
                            <td>"""+str(attachment)+"""</td>
                            <td>"""+str(items['date'])+"""</td>
                        </tr>"""

    cur.execute("select projects.items.* ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where projects.items.collection ="+str(id)+" order by projects.items.item_id")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse1.append(columnValue)

    columnHtml = """ """
    columnHtml += """
 			<th style="width: 12%">ID</th>
 			<th>Project</th>
            <th style="width: 13%">Date</th>
 			<th>Description</th>
 			<th>Priority</th>
 			<th>Estimate</th>
 			<th>Actual</th>
 			<th>Assignee</th>
 			<th>Status</th>
 			<th>Type</th>
        """

    itemHtml = """ """
    html1 = """ """
    html2 = """ """
    html3 = """ """
    html4 = """ """
    html5 = """ """
    html1Count = 0
    html2Count = 0
    html3Count = 0
    html4Count = 0
    html5Count = 0
    for items in finalResponse1:
        if(items['type'] == 1):
            html1Count += 1
            html1 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                        <td>"""+str(items['type_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 2):
            html2Count += 1
            html2 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                        <td>"""+str(items['type_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 3):
            html3Count += 1
            html3 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                        <td>"""+str(items['type_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 4):
            html4Count += 1
            html4 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                        <td>"""+str(items['type_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 5):
            html5Count += 1
            html5 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                        <td>"""+str(items['type_name'])+"""</td>
                    </tr>"""

    # app.logger.info("finalResponse1 ==> %s" , itemHtml)
    html = """ """
    html += """<!DOCTYPE html>
 <html>
 <head>
    <meta http-equiv='cache-control' content='no-cache'>
    <meta http-equiv='expires' content='0'>
    <meta http-equiv='pragma' content='no-cache'>
 	<style>
 		table {
 			font-family: arial, sans-serif;
 			border-collapse: collapse;
 			width: 100%;
 		}

 		td, th {
 			border: 1px solid #dddddd;
 			text-align: left;
 			padding: 8px;
 		}

 		.tableCollection{
 			width:80%;margin-left: auto;margin-right: auto;
 		}
        .collectionHtml th{
                background: #ddeaef;
                color: gray;
                width: 25%
        }
 	</style>
 </head>
 <body>
 	<h1 style="text-align: center;color: gray;">"""+collectionName+"""</h1>
     <br>
 	<table class="tableCollection">
 		"""+collectionHtml+"""
 	</table>

<br>
 	<br>
        """

    if html1Count > 0:
        html += """<h2 style="color: gray;">Story ( """+str(html1Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html1+"""
        </table>
        <br>"""
    if html2Count > 0:
        html += """<h2 style="color: gray;">Text ( """+str(html2Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html2+"""
    </table>
    <br>"""

    if html3Count > 0:
        html += """<h2 style="color: gray;">Bug ( """+str(html3Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html3+"""
    </table>
    <br>"""

    if html4Count > 0:
        html += """<h2 style="color: gray;">Minor ("""+str(html4Count)+""")</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html4+"""
    </table>
    <br>"""

    if html5Count > 0:
        html += """<h2 style="color: gray;">Block ( """+str(html5Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html5+"""
    </table>"""
    html += """<br>
 	<br>
 	<h2 style="color: gray;">Item's Comments/Attachment </h2>
 	<table>
 		<tr class="collectionHtml">
            <th>Item Id</th>
 			<th>Comment</th>
 			<th>Attachment</th>
 			<th>Date</th>
 		</tr>
 		"""+commentHtmlItems+"""
 	</table>
     <br>
 	<br>
 	<h2 style="color: gray;">Collection's Comments/Attachment </h2>
 	<table>
 		<tr class="collectionHtml">
 			<th>Comment</th>
 			<th>Attachment</th>
 			<th>Date</th>
 		</tr>
 		"""+commentHtml+"""
 	</table>
 </body>
 </html>
"""
    # app.logger.info("attachment ==> %s",html)

    filepath = r''+app.config['UPLOAD_FOLDER'] + \
        "collection/html/collection.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"collection/pdf/collection.pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        "enable-local-file-access": "",
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape',
        'margin-top': '15mm',
        'margin-bottom': '15mm'
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    con.close()
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"collection/pdf/", filename="collection.pdf")


@endpointV2.route('/v2/getAllCollectionPdf', methods=['POST'])
def get_all_collection_pdf():
    content = request.get_json(silent=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "collection/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "collection/pdf").mkdir(parents=True, exist_ok=True)

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    html = """ """
    for items in content.get("data"):
        finalResponse = []
        finalResponse1 = []
        finalResponse2 = []
        collectionName = None
        # app.logger.info("item ==> %s",items['projects'])
        collectionHtml = """ """
        collectionName = str(items["collection"])
        collectionHtml += """<tr class="collectionHtml">
                            <th>Collection Id</th>
                            <td>"""+str(items["collection"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Goals/Description</th>
                            <td>"""+str(items["description"])+"""</td>
                        </tr class="collectionHtml">
                        <tr class="collectionHtml">
                            <th>Projects</th>
                            <td>"""+listToStringWithoutBrackets(str(items["project_name"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>From</th>
                            <td>"""+format_date(str(items["from_date"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>To</th>
                            <td>"""+format_date(str(items["to_date"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Status</th>
                            <td>"""+str(items["status_name"])+"""</td>
                        </tr> """

        cur.execute(
            "SELECT * from projects.collection_attachment  WHERE collection_id ="+str(items["id"]))
        colnames = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        result = []
        for item1 in rows:
            columnValue = {}
            for index, item in enumerate(item1):
                columnValue[colnames[index]] = item
            finalResponse.append(columnValue)

        commentHtml = """ """
        for items1 in finalResponse:
            attachment = ""
            imageUrl = None
            if str(items1['attachment']) != "":
                file_name, file_extension = os.path.splitext(
                    str(items1['attachment']))
                if file_extension == ".png" or file_extension == ".jpg":
                    # imageUrl = Production.host+"ai/api/v2/downloadAttachment/"+str(id)+"/"+str(items1['attachment'])
                    imageUrl = app.config['UPLOAD_FOLDER'] + \
                        "attachments/"+str(id)+"/"+str(items1['attachment'])
                    attachment = """<img src=" """+imageUrl+"""" width="250" height="120"></img>"""
                else:
                    imageUrl = Production.host+"ai/api/v2/downloadAttachment/" + \
                        str(id)+"/"+str(items1['attachment'])
                    attachment = imageUrl

            commentHtml += """<tr>
                                <td>"""+str(items1['comment'])+"""</td>
                                <td>"""+str(attachment)+"""</td>
                                <td>"""+str(items1['date'])+"""</td>
                            </tr>"""

        cur.execute(
            "select projects.items.* ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id  where projects.items.collection ="+str(items["id"]))
        colnames = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        result = []
        for item1 in rows:
            columnValue = {}
            for index, item in enumerate(item1):
                columnValue[colnames[index]] = item
            finalResponse1.append(columnValue)

        columnHtml = """ """
        columnHtml += """
 			<th style="width: 12%">ID</th>
                <th>Project</th>
                <th style="width: 13%">Date</th>
                <th>Description</th>
                <th>Priority</th>
                <th>Estimate</th>
                <th>Actual</th>
                <th>Assignee</th>
                <th>Status</th>
                <th>Type</th>
        """
        itemHtml = """ """
        html1 = """ """
        html2 = """ """
        html3 = """ """
        html4 = """ """
        html5 = """ """
        html1Count = 0
        html2Count = 0
        html3Count = 0
        html4Count = 0
        html5Count = 0

        for items2 in finalResponse1:
            if(items2['type'] == 1):
                html1Count += 1
                html1 += """<tr>
                        <td>"""+str(items2['item_id'])+"""</td>
                        <td>"""+str(items2['project_name'])+"""</td>
                        <td>"""+format_date(str(items2['date']))+"""</td>
                        <td>"""+str(items2['description'])+"""</td>
                        <td>"""+str(items2['priority_name'])+"""</td>
                        <td>"""+str(items2['estimate'])+"""</td>
                        <td>"""+str(items2['actual'])+"""</td>
                        <td>"""+str(items2['assignee'])+"""</td>
                        <td>"""+str(items2['status_name'])+"""</td>
                        <td>"""+str(items2['type_name'])+"""</td>
                    </tr>"""
            elif(items2['type'] == 2):
                html2Count += 1
                html2 += """<tr>
                        <td>"""+str(items2['item_id'])+"""</td>
                        <td>"""+str(items2['project_name'])+"""</td>
                        <td>"""+format_date(str(items2['date']))+"""</td>
                        <td>"""+str(items2['description'])+"""</td>
                        <td>"""+str(items2['priority_name'])+"""</td>
                        <td>"""+str(items2['estimate'])+"""</td>
                        <td>"""+str(items2['actual'])+"""</td>
                        <td>"""+str(items2['assignee'])+"""</td>
                        <td>"""+str(items2['status_name'])+"""</td>
                        <td>"""+str(items2['type_name'])+"""</td>
                    </tr>"""
            elif(items2['type'] == 3):
                html3Count += 1
                html3 += """<tr>
                        <td>"""+str(items2['item_id'])+"""</td>
                        <td>"""+str(items2['project_name'])+"""</td>
                        <td>"""+format_date(str(items2['date']))+"""</td>
                        <td>"""+str(items2['description'])+"""</td>
                        <td>"""+str(items2['priority_name'])+"""</td>
                        <td>"""+str(items2['estimate'])+"""</td>
                        <td>"""+str(items2['actual'])+"""</td>
                        <td>"""+str(items2['assignee'])+"""</td>
                        <td>"""+str(items2['status_name'])+"""</td>
                        <td>"""+str(items2['type_name'])+"""</td>
                    </tr>"""
            elif(items2['type'] == 4):
                html4Count += 1
                html4 += """<tr>
                        <td>"""+str(items2['item_id'])+"""</td>
                        <td>"""+str(items2['project_name'])+"""</td>
                        <td>"""+format_date(str(items2['date']))+"""</td>
                        <td>"""+str(items2['description'])+"""</td>
                        <td>"""+str(items2['priority_name'])+"""</td>
                        <td>"""+str(items2['estimate'])+"""</td>
                        <td>"""+str(items2['actual'])+"""</td>
                        <td>"""+str(items2['assignee'])+"""</td>
                        <td>"""+str(items2['status_name'])+"""</td>
                        <td>"""+str(items2['type_name'])+"""</td>
                    </tr>"""
            elif(items2['type'] == 5):
                html5Count += 1
                html5 += """<tr>
                        <td>"""+str(items2['item_id'])+"""</td>
                        <td>"""+str(items2['project_name'])+"""</td>
                        <td>"""+format_date(str(items2['date']))+"""</td>
                        <td>"""+str(items2['description'])+"""</td>
                        <td>"""+str(items2['priority_name'])+"""</td>
                        <td>"""+str(items2['estimate'])+"""</td>
                        <td>"""+str(items2['actual'])+"""</td>
                        <td>"""+str(items2['assignee'])+"""</td>
                        <td>"""+str(items2['status_name'])+"""</td>
                        <td>"""+str(items2['type_name'])+"""</td>
                    </tr>"""

        html += """<!DOCTYPE html>
    <html>
    <head>
    <meta http-equiv='cache-control' content='no-cache'>
    <meta http-equiv='expires' content='0'>
    <meta http-equiv='pragma' content='no-cache'>
        <style>
            table {
                font-family: arial, sans-serif;
                border-collapse: collapse;
                width: 100%;
            }

            td, th {
                border: 1px solid #dddddd;
                text-align: left;
                padding: 8px;
            }

            .tableCollection{
                width:80%;margin-left: auto;margin-right: auto;
            }
            .collectionHtml th{
                background: #ddeaef;
                color: gray;
                width: 25%
        }
        </style>
    </head>
    <body>
        <h1 style="text-align: center; color: gray;">"""+collectionName+"""</h1>
        <br>
        <table class="tableCollection">
            """+collectionHtml+"""
        </table>

    <br>
        <br>"""

        if html1Count > 0:
            html += """<h2 style="color: gray;">Story ( """+str(html1Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html1+"""
        </table>
        <br>"""
        if html2Count > 0:
            html += """<h2 style="color: gray;">Text ( """+str(html2Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html2+"""
        </table>
        <br>"""

        if html3Count > 0:
            html += """<h2 style="color: gray;">Bug ( """+str(html3Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html3+"""
        </table>
        <br>"""

        if html4Count > 0:
            html += """<h2 style="color: gray;">Minor ("""+str(html4Count)+""")</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html4+"""
        </table>
        <br>"""

        if html5Count > 0:
            html += """<h2 style="color: gray;">Block ( """+str(html5Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html5+"""
        </table>"""

        html += """<br>
        <br>
        <h2 style="color: gray;">Comments/Attachment</h2>
        <table>
            <tr class="collectionHtml">
                <th>Comment</th>
                <th>Attachment</th>
                <th>Date</th>
            </tr>
            """+commentHtml+"""
        </table>
        <div style = "display:block; clear:both; page-break-after:always;"></div>
    </body>
    </html>
    """
        # app.logger.info("attachment ==> %s",html)

        filepath = r''+app.config['UPLOAD_FOLDER'] + \
            "collection/html/collection2.html"
        filepath1 = r''+app.config['UPLOAD_FOLDER'] + \
            "collection/pdf/collection2.pdf"
        with open(filepath, "w") as file:
            file.write(html)
    now = datetime.now()
    options = {
        "enable-local-file-access": "",
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'footer-right': '[page]',
        'orientation': 'landscape',
        'margin-top': '15mm',
        'margin-bottom': '15mm'
    }
    pdfkit.from_file(filepath, filepath1, options=options)
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getProjectItemwisePdf/<projectId>', methods=['GET'])
def getProjectItemwisePdf(projectId):
    columnValue = []
    # columnList = content.get('columnDef')
    # name = content.get('name')
    projectName = ''
    projectHtml = """ """
    finalResponse2 = SQLHelpers.getInstance().executeQuery('SELECT projects.projects.* , (select date from projects.items where project = projects.projects.id order by id desc limit 1) as last_item, ( select count(*) from projects.items where project = projects.projects.id and status != 6) as open, ( select count(*) from projects.items where projects.items.priority = 2 and project = projects.projects.id) as low, ( select count(*) from projects.items where projects.items.priority = 3 and project = projects.projects.id) as medium, ( select count(*) from projects.items where projects.items.priority = 4 and project = projects.projects.id) as high, (select count(*) from projects.collections where projects.projects.id = Any(projects.collections.projects)) as collection ,projects.methodology.name as methodology_name FROM projects.projects left join projects.methodology on projects.projects.methodology_id = projects.methodology.id where projects.projects.id ='+str(projectId))

    for items in finalResponse2:
        projectName = str(items["project_name"])
        projectHtml += """<tr class="collectionHtml">
                            <th class="tableTh">Project Name</th>
                            <td>"""+str(items["project_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th class="tableTh">Description</th>
                            <td>"""+str(items["description"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th class="tableTh">Team</th>
                            <td>"""+str(items["team"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th class="tableTh">Last Item Close</th>
                            <td>"""+str(items["last_closed_date"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th class="tableTh">Next Item</th>
                            <td>"""+str(items["nextitem"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th class="tableTh">Methodology</th>
                            <td>"""+str(items["methodology_name"])+"""</td>
                        </tr> """

        if items["last_item"] != None:
            projectHtml += """<tr class="collectionHtml">
                <th class="tableTh">Last Item</th>
                <td>"""+format_date(str(items["last_item"]))+"""</td>
            </tr>"""

    columnHtml = """ """
    columnHtml += """
        <th>ID</th>
        <th>Project</th>
        <th>Date</th>
        <th>Description</th>
        <th>Priority</th>
        <th>Estimate</th>
        <th>Actual</th>
        <th>Assignee</th>
        <th>Collection</th>
        <th>Status</th>
        """

    finalResponse = SQLHelpers.getInstance().executeQuery('select projects.items.*, (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , projects.users.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id where projects.items.project ='+str(projectId))

    html1 = """ """
    html2 = """ """
    html3 = """ """
    html4 = """ """
    html5 = """ """
    html1Count = 0
    html2Count = 0
    html3Count = 0
    html4Count = 0
    html5Count = 0
    for items in finalResponse:
        if(items['type'] == 1):
            html1Count += 1
            html1 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['collection_name'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 2):
            html2Count += 1
            html2 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['collection_name'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 3):
            html3Count += 1
            html3 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['collection_name'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 4):
            html4Count += 1
            html4 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['collection_name'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                    </tr>"""
        elif(items['type'] == 5):
            html5Count += 1
            html5 += """<tr>
                        <td>"""+str(items['item_id'])+"""</td>
                        <td>"""+str(items['project_name'])+"""</td>
                        <td>"""+format_date(str(items['date']))+"""</td>
                        <td>"""+str(items['description'])+"""</td>
                        <td>"""+str(items['priority_name'])+"""</td>
                        <td>"""+str(items['estimate'])+"""</td>
                        <td>"""+str(items['actual'])+"""</td>
                        <td>"""+str(items['assignee'])+"""</td>
                        <td>"""+str(items['collection_name'])+"""</td>
                        <td>"""+str(items['status_name'])+"""</td>
                    </tr>"""

    html = """ """

    Path(app.config['UPLOAD_FOLDER'] +
         "projectItemWise/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "projectItemWise/pdf").mkdir(parents=True, exist_ok=True)

    html += """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv='cache-control' content='no-cache'>
        <meta http-equiv='expires' content='0'>
        <meta http-equiv='pragma' content='no-cache'>
    <style>
        table {
        font-family: arial, sans-serif;
        border-collapse: collapse;
        width: 100%;
        }

        td, th {
        border: 1px solid #dddddd;
        text-align: left;
        padding: 8px;
        }

        .tableTh{
            font-weight: normal !important;
        }

        .tableCollection{
        width:80%;margin-left: auto;margin-right: auto;
        }
            .collectionHtml th{
                    background: #ddeaef;
                    color: gray;
                    width: 1%;
            }
    </style>
    </head>
    <body>
    <h1 style="text-align: center;color: gray;">"""+projectName+"""</h1>
        <br>
     <table class="tableCollection">
            """+projectHtml + """
     </table>   
     <br>"""

    if html1Count > 0:
        html += """<h2 style="color: gray;">Story ( """+str(html1Count)+""" )</h2>
        <br>
        <table>
            <tr class="collectionHtml">
            """+columnHtml+"""
            </tr>
                """+html1+"""
        </table>
        <br>"""
    if html2Count > 0:
        html += """<h2 style="color: gray;">Text ( """+str(html2Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html2+"""
    </table>
    <br>"""

    if html3Count > 0:
        html += """<h2 style="color: gray;">Bug ( """+str(html3Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html3+"""
    </table>
    <br>"""

    if html4Count > 0:
        html += """<h2 style="color: gray;">Minor ("""+str(html4Count)+""")</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html4+"""
    </table>
    <br>"""

    if html5Count > 0:
        html += """<h2 style="color: gray;">Block ( """+str(html5Count)+""" )</h2>
    <br>
    <table>
        <tr class="collectionHtml">
        """+columnHtml+"""
        </tr>
            """+html5+"""
    </table>"""

    html += """</body>
    </html>
"""
    filepath = r''+app.config['UPLOAD_FOLDER'] + \
        "projectItemWise/html/projectItemWise.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER'] + \
        "projectItemWise/pdf/projectItemWise.pdf"
    with open(filepath, "w") as file:
        file.write(html)
    now = datetime.now()
    options = {
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape',
        'margin-top': '15mm',
        'margin-bottom': '15mm',
    }
    pdfkit.from_file(filepath, filepath1, options=options)

    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"projectItemWise/pdf/", filename="projectItemWise.pdf")


@endpointV2.route('/v2/addLicense/<userID>', methods=['POST'])
def addLicense(userID):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.licenses (product, supplier, version, instance, usage,url, comments, created_on, created_by) values(%s,%s,%s,%s,%s,%s,%s,%s,%s)', (content.get(
        'product'), content.get('supplier'), content.get('version'),  content.get('instance'), content.get('usage'), content.get('url'), content.get('comments'), now.strftime("%m-%d-%Y %I:%M %p"), userID))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteTeamMember/<id>', methods=['DELETE'])
def deleteTeamMember(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.team_members WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteTeam/<id>', methods=['DELETE'])
def delete_team(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.teams WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteLicense/<id>', methods=['DELETE'])
def deleteLicense(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.licenses WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getTeamById/<id>', methods=['GET'])
def getTeamById(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.team_members where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getLicenseById/<id>', methods=['GET'])
def getLicenseById(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.licenses where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateTeam/<id>', methods=['PUT'])
def updateTeam(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.team_members set name=%s, title=%s, team=%s, email=%s, info=%s, location=%s, reports_to=%s where id =%s', (content.get(
        'name'), content.get('title'), content.get('team'), content.get('email'), content.get('info'), content.get('location'), content.get('reports_to'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateLicense/<id>', methods=['PUT'])
def updateLicense(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.licenses set product =%s, supplier =%s, version =%s, instance =%s, usage =%s,url =%s, comments =%s where id =%s', (content.get(
        'product'), content.get('supplier'), content.get('version'),  content.get('instance'), content.get('usage'), content.get('url'), content.get('comments'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addStack/<userID>', methods=['POST'])
def addStacks(userID):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.stacks (stack_id, projects, technology, created_by , info, created_on) values(%s,%s,%s,%s, %s,%s)',
                                                  (content.get('stack_id'), content.get('projects'), content.get('technology'), userID, content.get('info'), now.strftime("%m-%d-%Y %I:%M %p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getStackList/<id>', methods=['GET'])
def getStacksList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.stacks.* ,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.stacks.projects) project LEFT JOIN projects.projects u on u.id = project), projects.users.username from projects.stacks left join projects.users on projects.stacks.created_by = projects.users.id where created_by ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteStack/<id>', methods=['DELETE'])
def deleteStack(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.stacks WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getStackById/<id>', methods=['GET'])
def getStackById(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.stacks where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateStack/<id>', methods=['PUT'])
def updateStack(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.stacks set stack_id =%s, projects =%s, technology =%s, info=%s where id =%s',
                (content.get('stack_id'), content.get('projects'), content.get('technology'), content.get('info'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updatePageInfo/<id>', methods=['PUT'])
def updatePageInfo(id):
    content = request.get_json(silent=True)
    now = datetime.now()
    rows = SQLHelpers.getInstance().executeUpdate('update PROJECTS.created_page set title=%s , url= %s , pageid=%s, projectinfo=%s, projects=%s where id = %s',
                                                  (content.get('title'), content.get('url'), content.get('pageId'), content.get('projectInfo'), content.get('projects'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/saveQuickNotes', methods=['POST'])
def saveQuickNotes():
    content = request.get_json(silent=True)
    json_object = json.dumps(content.get('notes'), indent=4)
    rows = SQLHelpers.getInstance().executeUpdate(
        'Insert into PROJECTS.quick_notes (created_by, notes) values(%s,%s)', (content.get('userId'), json_object))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateQuickNotes/<id>', methods=['PUT'])
def updateQuickNotes(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    json_object = json.dumps(content.get('notes'), indent=4)
    cur.execute(
        'update projects.quick_notes set notes =%s where created_by =%s', (json_object, id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getQuickNotes/<userId>', methods=['GET'])
def getQuickNotes(userId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.quick_notes where created_by ="+userId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/quickNotesExist/<userId>', methods=['GET'])
def quickNotesExist(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeRawResult(
        "select * from projects.quick_notes where created_by = "+str(userId))
    toggle = False
    if rows is not None and len(rows) > 0:
        toggle = True
    return jsonify({'code': "200", 'message': "success", "existUrl": toggle})


@endpointV2.route('/v2/getFileById/<id>', methods=['GET'])
def get_file_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.upload_file where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateScriptUploadData/<id>', methods=['PUT'])
def update_script_upload_data(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    json_object = json.dumps(content.get('data'), indent=4)
    cur.execute(
        'update projects.upload_file set data =%s where id =%s', (json_object, id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateScriptUpload/<id>', methods=['PUT'])
def script_upload_update(id):
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"upload/" +
             content.get("userId")+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"upload/"+content.get("userId")+"/", scriptFile.filename.lower()))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"upload/"+content.get("userId")+"/", scriptFile.filename.lower()), "upload/"+content.get("userId")+"/"+scriptFile.filename.lower())
        attachment = scriptFile.filename

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()

    json_object = json.dumps(content.get('data'), indent=4)
    cur.execute("update PROJECTS.upload_file set project_id=%s, description=%s, file_type=%s, file_name=%s where id=%s",
                (content.get("project"), content.get("file_description"), content.get("file_type"), attachment, id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getAllUserList', methods=['GET'])
def get_user_list():
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.users ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllAssigneeList/<id>', methods=['GET'])
def getAllAssigneeList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, name as label from projects.team_members where team && (select team from projects.projects where id ="+str(id)+")  and active = 'true'")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsByProject/<id>', methods=['GET'])
def getItemsByProject(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id, item_id from projects.items where project="+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllStatus/<id>', methods=['GET'])
def getAllStatus(id):
    finalResponse = []
    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.statuslist.user_id="+str(id)+" or projects.statuslist.users="+str(
            id)+" or projects.statuslist.projects && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.statuslist.user_id =" + \
                str(id)+" or projects.statuslist.users="+str(id) + \
                " or projects.statuslist.projects && (select array_agg(id) from projects.projects where created_by ='"+str(
                    id)+"')"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.statuslist.user_id =" + \
                str(id)+" or projects.statuslist.users="+str(id)
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.statuslist.*,(select array_agg(projects.items.item_id) as status_detail_item from projects.status_details left join projects.items on projects.status_details.item = projects.items.id where status_id = projects.statuslist.id),(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.statuslist.projects) project LEFT JOIN projects.projects u on u.id = project) ,projects.cycle.Name as cycle_name ,projects.users.username, projects.users.name from projects.statuslist left join projects.users on projects.statuslist.users = projects.users.id left join projects.cycle on projects.statuslist.cycle = projects.cycle.id "+str(query) + " order by projects.statuslist.id desc ;")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/saveStatus/<userId>', methods=['POST'])
def saveStatus(userId):
    content = request.get_json(silent=True)
    now = datetime.now()
    json_object = json.dumps(content.get('rows'), indent=4)
    rows1 = SQLHelpers.getInstance().executeRawResult(
        "select count(*) from projects.statuslist where date='"+content.get('date')+"'")
    if rows1[0][0] == 0:
        statusId = content.get('statusId')
    else:
        statusId = content.get('statusId')+"-"+str(rows1[0][0])
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.StatusList (status_id, user_id, projects, cycle, from_date, to_date, date, users, rows, created_on, status_date) values(%s, %s, %s, %s, NULLIF(%s, \'\')::date,  NULLIF(%s, \'\')::date,  NULLIF(%s, \'\')::date, %s, %s,%s, NULLIF(%s, \'\')::date) returning id',
                                                  (statusId, userId, content.get('projects'), content.get('cycle'), content.get('from'), content.get('to'), content.get('date'), content.get('user'), json_object, now.strftime("%m-%d-%Y %I:%M %p"), content.get('status_date')))
    id = rows[0][0]
    for item in content.get('rows'):
        SQLHelpers.getInstance().executeUpdate('Insert into projects.status_details (status, project, info, description, item, status_id) values(%s, %s, %s, %s, %s, %s)',
                                               (item['status'], item['project'], item['info'], item['description'], item['item'], id))
        if item['status'] == '3':
            SQLHelpers.getInstance().executeUpdate(
                'update projects.items set blocked=%s where id = %s', (True, item['item']))
            rows = SQLHelpers.getInstance().executeRawResult(
                'select item_id, description from projects.items where id ='+str(item["item"]))
            ref_id = rows[0][0]
            description = rows[0][1]
            li = []
            li.append(int(item['project']))
            SQLHelpers.getInstance().executeUpdate('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information, activity_id, reference_id, reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                                   (li, userId, ref_id+" marked as Blocked", ref_id, now, now.strftime("%I:%M %p"), description, '9', item['item'], 'I', 'Item Updated'))

    if (content.get("tempAttachment") is not None and len(content.get("tempAttachment")) > 0):
        for fileAttach in content.get("tempAttachment"):
            try:
                Path(app.config['UPLOAD_FOLDER']+"status/attachments/" +
                     str(id)+"/").mkdir(parents=True, exist_ok=True)
                shutil.move(app.config['UPLOAD_FOLDER']+"temp/"+userId+"/"+fileAttach,
                            app.config['UPLOAD_FOLDER']+"status/attachments/"+str(id)+"/"+fileAttach)
                S3Client.upload_file(os.path.join(
                    app.config['UPLOAD_FOLDER']+"status/attachments/"+str(id)+"/", fileAttach), "status/attachments/"+str(id)+"/"+fileAttach)
                SQLHelpers.getInstance().executeUpdate('INSERT INTO PROJECTS.status_attachment (status_id, notes, attachment, DATE, created_by) VALUES (%s, %s, %s,%s, %s)',
                                                       (str(id), '', fileAttach, now, userId))
            except Exception as ex:
                app.logger.info(
                    "Error in moving temporary attachments: %s", traceback.format_exc())

    if (content.get("tempNotes") is not None and len(content.get("tempNotes")) > 0):
        for notes in content.get("tempNotes"):
            noteName = notes['note']
            SQLHelpers.getInstance().executeUpdate(
                'INSERT INTO PROJECTS.status_attachment (status_id, notes, attachment, DATE, created_by) VALUES (%s, %s, %s,%s, %s)', (str(id), noteName, '', now, userId))

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteStatus/<id>', methods=['DELETE'])
def delete_status(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        "DELETE FROM PROJECTS.status_details WHERE status_id = '" + id + "'")
    cur.execute("DELETE FROM PROJECTS.StatusList WHERE id = '" + id + "'")
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getStatusListById/<id>', methods=['GET'])
def get_status_list_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.statuslist where id = "+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateStatus/<id>', methods=['PUT'])
def update_status(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    json_object = json.dumps(content.get('rows'), indent=4)
    r1 = SQLHelpers.getInstance().executeRawResult(
        "select user_id from PROJECTS.StatusList where id = "+str(id))
    userId = r1[0][0]
    SQLHelpers.getInstance().executeUpdate('update PROJECTS.StatusList set projects=%s, cycle=%s, from_date = NULLIF(%s, \'\')::date, to_date = NULLIF(%s, \'\')::date, date = NULLIF(%s, \'\')::date, users=%s, rows=%s, status_date = NULLIF(%s, \'\')::date  where id = %s',
                                           (content.get('projects'), content.get('cycle'), content.get('from'), content.get('to'), content.get('date'), content.get('user'), json_object, content.get('status_date'), id))
    for item in content.get('rows'):
        if 'id' in item:
            SQLHelpers.getInstance().executeUpdate('update PROJECTS.status_details set status=%s, project=%s, info=%s, description=%s, item=%s where id=%s',
                                                   (item['status'], item['project'], item['info'], item['description'], item['item'], item['id']))
        else:
            SQLHelpers.getInstance().executeUpdate('Insert into projects.status_details (status, project, info, description,item, status_id) values(%s, %s, %s, %s, %s, %s)',
                                                   (item['status'], item['project'], item['info'], item['description'], item['item'], id))
        if item['status'] == '3':
            SQLHelpers.getInstance().executeUpdate(
                'update projects.items set blocked=%s where id = %s', (True, item['item']))
            rows = SQLHelpers.getInstance().executeRawResult(
                'select item_id, description from projects.items where id ='+str(item["item"]))
            ref_id = rows[0][0]
            description = rows[0][1]
            li = []
            li.append(int(item['project']))
            SQLHelpers.getInstance().executeUpdate('Insert into projects.stream (project_id, user_id, activity, reference, date, time, information, activity_id, reference_id, reference_type, action) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                                   (li, userId, ref_id+" marked as Blocked", ref_id, now, now.strftime("%I:%M %p"), description, '9', item['item'], 'I', 'Item Updated'))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getStatusStatus', methods=['GET'])
def get_status_status():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.status_status; ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/uploadStatusAttachment/<userId>', methods=['POST'])
def upload_status_attachment(userId):
    content = request.form
    now = datetime.now()
    attachment = None
    attachments = []
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"temp/"+userId +
             "/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            allFiles = request.files.getlist("file")
            # app.logger.info("multiple file attachment:: %s", allFiles)
            for sFile in allFiles:
                sFilename = sFile.filename
                attachment = sFilename[:sFilename.rindex(
                    ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
                app.logger.info("attachment file name:: %s", attachment)
                sFile.save(os.path.join(
                    app.config['UPLOAD_FOLDER']+"temp/"+userId+"/", attachment))
                attachments.append(attachment)
    else:
        attachment = ""

    return jsonify({'code': "200", 'message': "success", "attachmentName": attachments})


@endpointV2.route('/v2/getStatusAttachments/<itemId>', methods=['GET'])
def get_status_attachment(itemId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("SELECT projects.status_attachment.*,PROJECTS.USERS.name as username FROM projects.status_attachment left join PROJECTS.ITEMS on PROJECTS.ITEMS.id = projects.status_attachment.status_id left join PROJECTS.USERS on PROJECTS.USERS.id = PROJECTS.status_attachment.created_by   WHERE status_id="+itemId)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteStatusAttachment/<id>', methods=['GET'])
def delete_status_attachment(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.status_attachment WHERE id = '" + id + "'")
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateStatusAttachment/<itemId>/<id>', methods=['POST'])
def update_status_attachment(itemId, id):
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"status/attachments/" +
             itemId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"status/attachments/"+itemId+"/", scriptFile.filename))
            S3Client.upload_file(os.path.join(
                app.config['UPLOAD_FOLDER']+"status/attachments/"+itemId+"/", scriptFile.filename), "status/attachments/"+itemId+"/"+scriptFile.filename)
        attachment = scriptFile.filename

    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'Update projects.status_attachment set ATTACHMENT = %s where id =%s', (attachment, id))
    con.commit()
    # rows = cur.fetchall()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setStatusAttachment/<itemId>', methods=['POST'])
def set_status_attachment(itemId):
    content = request.form
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"status/attachments/" +
             itemId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            allFiles = request.files.getlist("file")
            for sFile in allFiles:
                sFilename = sFile.filename
                attachment = sFilename[:sFilename.rindex(
                    ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
                sFile.save(os.path.join(
                    app.config['UPLOAD_FOLDER']+"status/attachments/"+itemId+"/", attachment))
                S3Client.upload_file(os.path.join(
                    app.config['UPLOAD_FOLDER']+"status/attachments/"+itemId+"/", attachment), "status/attachments/"+itemId+"/"+attachment)
                # if content.get("comment") is not None and content.get("comment") != "":
                #     comment = content.get("comment")
                # else:
                #     comment = ""
                SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.status_attachment (status_ID, notes, ATTACHMENT, DATE, created_BY) VALUES (%s, %s, %s,%s, %s)',
                                                       (itemId, '', attachment, now.strftime("%m-%d-%Y %I:%M %p"), content.get("userId")))

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setStatusNotes/<itemId>', methods=['POST'])
def set_status_notes(itemId):
    content = request.get_json(silent=True)
    now = datetime.now()
    SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.status_attachment (status_ID, notes, ATTACHMENT, DATE, created_BY) VALUES (%s, %s, %s,%s, %s)',
                                           (itemId, content.get('notes'), '', now.strftime("%m-%d-%Y %I:%M %p"), content.get("userId")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCyclesList', methods=['GET'])
def get_cycle_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.cycle ;")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getStatusWisePdf/<id>/<name>', methods=['GET'])
def get_statusWise_pdf(id, name):
    content = request.get_json(silent=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "statusWise/html").mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER'] +
         "statusWise/pdf").mkdir(parents=True, exist_ok=True)

    finalResponse = []
    finalResponse1 = []
    finalResponse2 = []
    collectionName = None
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select projects.statuslist.*,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.statuslist.projects) project LEFT JOIN projects.projects u on u.id = project) ,projects.cycle.Name as cycle_name ,projects.users.username, 'Stat-' || projects.statuslist.id as stat_id, projects.users.name from projects.statuslist left join projects.users on projects.statuslist.users = projects.users.id left join projects.cycle on projects.statuslist.cycle = projects.cycle.id where projects.statuslist.id="+str(id)+" order by projects.statuslist.id desc ;")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()

    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse2.append(columnValue)

    collectionHtml = """ """
    Rows = []
    for items in finalResponse2:
        collectionName = str(items["stat_id"])
        Rows = items["rows"]
        collectionHtml += """<tr class="collectionHtml">
                            <th>Status Id</th>
                            <td>"""+str(items["stat_id"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Cycle</th>
                            <td>"""+str(items["cycle_name"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Projects</th>
                            <td>"""+listToStringWithoutBrackets(str(items["project_name"]))+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>From</th>
                            <td>"""+str(items["from_date"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>To</th>
                            <td>"""+str(items["to_date"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Date</th>
                            <td>"""+str(items["date"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>Status Date</th>
                            <td>"""+str(items["status_date"])+"""</td>
                        </tr>
                        <tr class="collectionHtml">
                            <th>User</th>
                            <td>"""+str(items["name"])+"""</td>
                        </tr> """

    rowHtml = """ """
    for item in Rows:
        app.logger.info("Rows ==> %s", item['project'])
        fRows = SQLHelpers.getInstance().executeRawResult("select name, (select project_name from projects.projects where id = " +
                                                          str(item['project'])+"), (select item_id from projects.items where id = "+str(item['item'])+") from projects.status_status where id ="+str(item['status'])+";")
        name = fRows[0][0]
        project_name = fRows[0][1]
        item_id = fRows[0][2]
        rowHtml += """<tr>
                            <td>"""+str(name)+"""</td>
                            <td>"""+str(project_name)+"""</td>
                            <td>"""+str(item_id)+"""</td>
                            <td>"""+str(item['info'])+"""</td>
                            <td>"""+str(item['description'])+"""</td>
                        </tr>"""

    cur.execute(
        "SELECT * from projects.status_attachment WHERE status_id ="+str(id))
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)

    commentHtml = """ """
    for items in finalResponse:
        attachment = ""
        imageUrl = None
        if str(items['attachment']) != "":
            file_name, file_extension = os.path.splitext(
                str(items['attachment']))
            if file_extension == ".png" or file_extension == ".jpg":
                imageUrl = app.config['UPLOAD_FOLDER'] + \
                    "attachments/"+str(id)+"/"+str(items['attachment'])
                attachment = """<img src='"""+imageUrl+"""' width="250" height="120"></img>"""
            else:
                imageUrl = Production.host+"ai/api/v2/downloadAttachment/" + \
                    str(id)+"/"+str(items['attachment'])
                attachment = str(imageUrl)

        commentHtml += """<tr>
                            <td>"""+str(items['notes'])+"""</td>
                            <td>"""+attachment+"""</td>
                            <td>"""+str(items['date'])+"""</td>
                        </tr>"""

    html = """<!DOCTYPE html>
 <html>
 <head>
    <meta http-equiv='cache-control' content='no-cache'>
    <meta http-equiv='expires' content='0'>
    <meta http-equiv='pragma' content='no-cache'>
    <meta http-equiv='Content-type' content='text/html; charset=utf-8' />
 	<style>
 		table {
 			font-family: arial, sans-serif;
 			border-collapse: collapse;
 			width: 100%;
 		}

 		td, th {
 			border: 1px solid #dddddd;
 			text-align: left;
 			padding: 8px;
 		}

 		.tableCollection{
 			width:80%;margin-left: auto;margin-right: auto;
 		}
        .collectionHtml th{
                background: #ddeaef;
                color: gray;
                width: 25%
        }
 	</style>
 </head>
 <body>
 	<h1 style="text-align: center; color:gray">"""+collectionName+"""</h1>
     <br>
 	<table class="tableCollection">
 		"""+collectionHtml+"""
 	</table>
     <br>
     <br>
     <table>
 		<tr class="collectionHtml">
 			<th>Status</th>
 			<th>Project</th>
 			<th>Item</th>
            <th>Info</th>
            <th>Description</th>
 		</tr>
 		"""+rowHtml+"""
 	</table>
 	<br>
    <br>
 	<h2 style="color:gray;">Notes/Attachment</h2>
 	<table>
 		<tr class="collectionHtml">
 			<th>Note</th>
 			<th>Attachment</th>
 			<th>Date</th>
 		</tr>
 		"""+commentHtml+"""
 	</table>
 </body>
 </html>
"""
    # app.logger.info("attachment ==> %s",html)

    filepath = r''+app.config['UPLOAD_FOLDER']+"statusWise/html/status.html"
    filepath1 = r''+app.config['UPLOAD_FOLDER']+"statusWise/pdf/status.pdf"
    with open(filepath, mode="w", encoding="utf-8") as file:
        file.write(html)
    now = datetime.now()
    options = {
        "enable-local-file-access": "",
        'header-right': now.strftime("%m-%d-%Y"),
        'header-font-size': '7',
        'orientation': 'landscape',
    }
    pdfkit.from_file(filepath, filepath1, options=options)
    con.close()
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"statusWise/pdf/", filename="status.pdf")


@endpointV2.route('/v2/getAllProjectList', methods=['GET'])
def get_all_project_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, project_name as label from projects.projects ;")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllItemList', methods=['GET'])
def get_all_item_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value , item_id as label from projects.items ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllCollectionList', methods=['GET'])
def get_all_collection_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, collection as label from projects.collections ;")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllPageList', methods=['GET'])
def get_all_page_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value , pageid as label from projects.created_page ;")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getModelList/<id>', methods=['GET'])
def get_model_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select *, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.models.projects) project LEFT JOIN projects.projects u on u.id = project) , (select count(*) from projects.model_fields where model_id = projects.models.id ) from PROJECTS.models where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getModelFieldList/<id>', methods=['GET'])
def get_model_fields_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.model_fields where model_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllModelFields/<id>', methods=['GET'])
def get_all_model_fields(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select projects.model_fields.*, projects.models.model_name from PROJECTS.model_fields left join projects.models on projects.model_fields.model_id = projects.models.id where projects.models.user_id = '+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllModelFieldById/<id>', methods=['GET'])
def get_all_model_field_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select projects.model_fields.*, projects.models.model_name from PROJECTS.model_fields left join projects.models on projects.model_fields.model_id = projects.models.id where projects.models.id = '+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getApiList/<id>', methods=['GET'])
def get_api_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select *, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.api.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.api where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getApiKeyList/<id>', methods=['GET'])
def get_api_key_ist(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.api_keys where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addModel/<userID>', methods=['POST'])
def addModel(userID):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.models (model_name, app, description, projects, datatable, database, user_id) values(%s,%s,%s,%s,%s,%s,%s) returning id',
                                                  (content.get('modelName'), content.get('app'), content.get('description'), content.get('project'), content.get('datatable'), content.get('database'), userID))
    id = rows[0][0]
    for item in content.get('rows'):
        SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.model_fields (field_name, type, relations, info, display_name, rules, last_used, model_id) values(%s,%s,%s,%s,%s,%s,%s,%s)',
                                               (item['field_name'], item['type'], item['relations'], item['info'], item['display_name'], item['rules'], item['last_used'], id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addApiKey/<userID>', methods=['POST'])
def add_api_key(userID):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.api_keys (api_source, api_key, info, user_id) values(%s,%s,%s,%s)',
                                                  (content.get('apiSource'), content.get('apiKey'), content.get('info'), userID))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addApi/<userID>', methods=['POST'])
def addApi(userID):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.api (api_name, version, endpoint, method, description, url, data_parameters, success_response, error_response, sample_call, info, projects, user_id,created_on) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', (content.get('api_name'), content.get(
        'version'), content.get('endpoint'), content.get('method'), content.get('description'), content.get('url'), content.get('data_parameters'), content.get('success_response'), content.get('error_response'), content.get('sample_call'), content.get('info'), content.get('project'), userID, now.strftime("%m-%d-%Y %I:%M %p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addModelField/<id>', methods=['POST'])
def add_model_fields(id):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.model_fields (field_name, type, relations, info, model_id) values(%s,%s,%s,%s,%s)',
                                                  (content.get('field_name'), content.get('type'), content.get('relations'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getModelById/<id>', methods=['GET'])
def get_model_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.models where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getModelFieldById/<id>', methods=['GET'])
def get_model_field_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.model_fields where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getApiById/<id>', methods=['GET'])
def get_api_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.api where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getApiKeyById/<id>', methods=['GET'])
def get_api_key_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.api_keys where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateModel/<id>', methods=['PUT'])
def update_model(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.models set model_name=%s, app=%s, description=%s, projects=%s, datatable=%s, database=%s where id=%s',
                                                           (content.get('modelName'), content.get('app'), content.get('description'), content.get('project'), content.get('datatable'), content.get('database'), id))
    for item in content.get('rows'):
        if 'id' in item:
            SQLHelpers.getInstance().executeUpdate('update PROJECTS.model_fields set field_name=%s, type=%s, relations=%s, info=%s, display_name=%s, rules=%s, last_used=%s where id=%s',
                                                   (item['field_name'], item['type'], item['relations'], item['info'], item['display_name'], item['rules'], item['last_used'], item['id']))
        else:
            SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.model_fields (field_name, type, relations, info,display_name, rules, last_used, model_id) values(%s,%s,%s,%s,%s,%s,%s,%s)',
                                                   (item['field_name'], item['type'], item['relations'], item['info'], item['display_name'], item['rules'], item['last_used'], id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateModelfields/<id>', methods=['PUT'])
def update_model_fields(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.model_fields set field_name=%s, type=%s, relations=%s, info=%s, display_name=%s, rules=%s, last_used=%s where id=%s',
                                                           (content.get('field_name'), content.get('type'), content.get('relations'), content.get('info'), content.get('display_name'), content.get('rules'), content.get('last_used'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateApiKey/<id>', methods=['PUT'])
def update_api_key(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.api_keys set api_source=%s, api_key=%s, info=%s where id=%s',
                                                           (content.get('apiSource'), content.get('apiKey'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateApi/<id>', methods=['PUT'])
def update_api(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.api set api_name=%s, version=%s, endpoint=%s, method=%s, description=%s, url=%s, data_parameters=%s, success_response=%s, error_response=%s, sample_call=%s, info=%s, projects=%s where id=%s ', (content.get('api_name'),
                                                                                                                                                                                                                                                                              content.get('version'), content.get('endpoint'), content.get('method'), content.get('description'), content.get('url'), content.get('data_parameters'), content.get('success_response'), content.get('error_response'), content.get('sample_call'), content.get('info'), content.get('project'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteModel/<id>', methods=['DELETE'])
def delete_model(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.models WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteApi/<id>', methods=['DELETE'])
def delete_api(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.api WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteApiKey/<id>', methods=['DELETE'])
def delete_api_key(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.api_keys WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteModelFieldsKey/<id>', methods=['DELETE'])
def delete_model_field(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.model_fields WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteContact/<id>', methods=['DELETE'])
def delete_contact(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.contacts WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteEvent/<id>', methods=['DELETE'])
def delete_event(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.events WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteApp/<id>', methods=['DELETE'])
def delete_app(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.apps WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteUrl/<id>', methods=['DELETE'])
def delete_url(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.urls WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getAllContactList/<id>', methods=['GET'])
def get_all_contact_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select *, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.contacts.projects) project LEFT JOIN projects.projects u on u.id = project) from PROJECTS.contacts where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addContact/<id>', methods=['POST'])
def add_contact(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.contacts (contact, organization, projects, phone, mobile, email, location, title,info, user_id, created_on) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', (content.get(
        'contact'), content.get('organization'), content.get('project'), content.get('phone'), content.get('mobile'), content.get('email'), content.get('location'), content.get('title'), content.get('info'), id, now.strftime("%m-%d-%Y %I:%M %p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateContact/<id>', methods=['PUT'])
def update_contact(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.contacts set contact=%s, organization=%s, projects=%s, phone=%s, mobile=%s, email=%s, location=%s, title=%s, info=%s where id=%s', (content.get(
        'contact'), content.get('organization'), content.get('project'), content.get('phone'), content.get('mobile'), content.get('email'), content.get('location'), content.get('title'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getContactById/<id>', methods=['GET'])
def get_contact_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.contacts where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getEventById/<id>', methods=['GET'])
def get_event_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.events where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAppById/<id>', methods=['GET'])
def get_app_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.apps where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getUrlById/<id>', methods=['GET'])
def get_url_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.urls where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addEvent/<userId>', methods=['POST'])
def add_event(userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.events (event_date, time_from, time_to, event_type, description, team_members, projects, items, info, user_id, created_on) values(NULLIF(%s, \'\')::date    ,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', (content.get(
        'event_date'), content.get('time_from'), content.get('time_to'), content.get('event_type'), content.get('description'), content.get('team_members'), content.get('project'), content.get('items'), content.get('info'), userId, now.strftime("%m-%d-%Y %I:%M %p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateEvent/<id>', methods=['PUT'])
def update_event(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.events set event_date = NULLIF(%s, \'\')::date, time_from=%s, time_to=%s, event_type=%s, description=%s, team_members=%s, projects=%s, items=%s, info=%s where id=%s',
                                                           (content.get('event_date'), content.get('time_from'), content.get('time_to'), content.get('event_type'), content.get('description'), content.get('team_members'), content.get('project'), content.get('items'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addUrl/<userId>', methods=['POST'])
def add_url(userId):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.urls (url, description, info, projects, items, user_id, created_on) values(%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('url'), content.get('description'), content.get('info'), content.get('project'), content.get('items'), userId, now.strftime("%m-%d-%Y %I:%M %p")))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addApp/<userId>', methods=['POST'])
def add_app(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.apps (app_name, app_url, instance, app_type, info, team_member, user_id) values(%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('app_name'), content.get('app_url'), content.get('instance'), content.get('app_type'), content.get('info'), content.get('team_member'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateApp/<id>', methods=['PUT'])
def update_app(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.apps set app_name=%s, app_url=%s, instance=%s, app_type=%s, info=%s, team_member=%s  where id=%s',
                                                           (content.get('app_name'), content.get('app_url'), content.get('instance'), content.get('app_type'), content.get('info'), content.get('team_member'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateUrl/<id>', methods=['PUT'])
def update_url(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.urls set url=%s, description=%s, info=%s, projects=%s, items=%s where id=%s',
                                                           (content.get('url'), content.get('description'), content.get('info'), content.get('project'), content.get('items'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getAllEventList/<id>', methods=['GET'])
def get_all_event_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.events.*, projects.event_types.name as event_type_name, (SELECT array_agg(u.name) as member_name FROM unnest(projects.events.team_members) member LEFT JOIN projects.team_members u on u.id = member), (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.events.projects) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.item_id) as item_name FROM unnest(projects.events.items) item LEFT JOIN projects.items u on u.id = item) from PROJECTS.events left join projects.event_types on projects.events.event_type = projects.event_types.id where projects.events.user_id ="+id+" order by projects.events.id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllAppList/<id>', methods=['GET'])
def get_all_app_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.apps.*,(SELECT array_agg(u.instance_id) as instance_name FROM unnest(projects.apps.instance) inst LEFT JOIN projects.instance u on u.id = inst), (SELECT array_agg(u.team) as member_name FROM unnest(projects.apps.team_member) tm LEFT JOIN projects.teams u on u.id = tm), projects.app_type.type_name as app_type_name  from PROJECTS.apps left join projects.app_type on projects.apps.app_type = projects.app_type.id  where user_id="+id+" order by projects.apps.id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllUrlList/<id>', methods=['GET'])
def get_all_url_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select *, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.urls.projects) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.item_id) as item_name FROM unnest(projects.urls.items) item LEFT JOIN projects.items u on u.id = item) from PROJECTS.urls where user_id ="+id+" order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMultipleProjectItems', methods=['POST'])
def get_multiple_project_items():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, item_id as label from projects.items where project= ANY(Array"+str(content.get('projects'))+")")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTeamMemberByProject', methods=['POST'])
def get_team_member_by_project():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select tm.id as value, tm.name as label from projects.team_members tm where team && (select array_agg(team) from projects.projects where id = ANY(Array"+str(content.get('projects'))+") and team is not null )")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllBranchesList/<id>', methods=['GET'])
def get_all_branches_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select *, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.branches.project) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.item_id) as item_name FROM unnest(projects.branches.items) item LEFT JOIN projects.items u on u.id = item) from PROJECTS.branches where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllGitActivtiyList/<id>', methods=['GET'])
def get_all_git_activity_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select *, projects.git_activity.action as git_action from PROJECTS.git_activity where user_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteGitAccounts/<id>/<type>', methods=['DELETE'])
def delete_git_accounts(id, type):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects."+type+" WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addBranch/<userId>', methods=['POST'])
def add_branch(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.branches (git_account, git_report, branch, merge_request, project, items, user_id) values(%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('git_account'), content.get('git_report'), content.get('branch'), content.get('merge_request'), content.get('project'), content.get('items'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateBranch/<id>', methods=['PUT'])
def update_branch(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.branches set git_account=%s, git_report=%s, branch=%s, merge_request=%s, project=%s, items=%s where id=%s',
                                                           (content.get('git_account'), content.get('git_report'), content.get('branch'), content.get('merge_request'), content.get('project'), content.get('items'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addGitActivity/<userId>', methods=['POST'])
def add_git_activity(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.git_activity (git_account, git_repo, branch, users, date, action, info, user_id) values(%s,%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('git_account'), content.get('git_repo'), content.get('branch'), content.get('users'), content.get('date'), content.get('action'), content.get('info'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateGitActivity/<id>', methods=['PUT'])
def update_git_activity(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.git_activity set git_account=%s, git_repo=%s, branch=%s, users=%s, date=%s, action=%s, info=%s where id=%s',
                                                           (content.get('git_account'), content.get('git_repo'), content.get('branch'), content.get('users'), content.get('date'), content.get('action'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getBranchById/<id>', methods=['GET'])
def get_branch_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.branches where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getGitActivityById/<id>', methods=['GET'])
def get_git_activity_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.git_activity where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllTeamsList/<id>', methods=['GET'])
def get_all_teams_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select *,(SELECT array_agg(u.project_name) as project_name FROM unnest(projects.teams.projects) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.name) as member_name FROM unnest(projects.teams.team_members) member LEFT JOIN projects.team_members u on u.id = member) from PROJECTS.teams where user_id ="+id+" order by team ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTeamsById/<id>', methods=['GET'])
def get_team_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.teams where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addTeams/<userId>', methods=['POST'])
def add_teams(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.teams (projects, team, team_members, info, user_id) values(%s,%s,%s,%s,%s)',
                                                  (content.get('projects'), content.get('team'), content.get('team_members'), content.get('info'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateTeams/<id>', methods=['PUT'])
def update_Team(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.teams set projects=%s, team=%s, team_members=%s, info=%s where id=%s',
                                                           (content.get('projects'), content.get('team'), content.get('team_members'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getMultipleTeamMember/<userId>', methods=['GET'])
def get_multiple_team_member(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, name as label from projects.team_members where created_by ="+userId+" and active = 'true' order by name")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMultipleCloudAccounts/<userId>', methods=['GET'])
def get_multiple_cloud_accounts(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, account as label from projects.cloud where created_by ="+userId)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/checkInstanceUnique/<value>/<userId>', methods=['GET'])
def checkInstanceUnique(value, userId):
    rows = []
    rows = SQLHelpers.getInstance().executeQuery("select id from projects.instance where created_by =" +
                                                 str(userId)+" and instance_id ='"+str(value)+"'")
    exist = None
    if len(rows) > 0:
        exist = True
    else:
        exist = False
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/getMultipleInstanceId/<userId>', methods=['GET'])
def get_multiple_id(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, instance_id as label from projects.instance where created_by ="+userId)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getMultipleTeam/<userId>', methods=['GET'])
def get_multiple_team(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, team as label from projects.teams where user_id ="+userId + " order by team")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAppList/<userId>', methods=['GET'])
def get_app_list(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, app_name as label from projects.apps where user_id ="+userId+" order by app_name ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getCollectionList/<userId>', methods=['GET'])
def get_collection_list(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, collection as label from projects.collections where user_id ="+userId)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTimeList/<id>', methods=['GET'])
def get_time_list(id):
    content = request.get_json(silent=True)
    finalResponse = []

    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE pt.user_id=" + \
            str(id)+" or pt.project && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE pt.user_id =" + \
                str(id)+" or pt.project && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
        elif userType == "I" and pInvite == False:
            query = "WHERE pt.user_id ="+str(id)
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select pt.*, 'Time-' || pt.id as time_id,projects.team_members.name as team_member_name, pc.project_code as projectCode, (SELECT array_agg(u.project_name) as project_name FROM unnest(pt.project) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.item_id) as item_name FROM unnest(pt.items) item LEFT JOIN projects.items u on u.id = item), (select array_agg(projects.time_attachment.attachment) as attachments from projects.time_attachment where pt.id = projects.time_attachment.time_id) from projects.time as pt left join projects.team_members on pt.team_member = projects.team_members.id left join PROJECTS.project_code pc on pc.id=pt.project_code "+query+" order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectCostList/<id>', methods=['GET'])
def get_project_cost_list(id):
    content = request.get_json(silent=True)
    finalResponse = []

    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.project_cost.user_id=" + \
            str(id)+" or projects.project_cost.project && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.project_cost.user_id =" + \
                str(id)+" or projects.project_cost.project && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.project_cost.user_id ="+str(id)
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.project_cost.*, 'Cost-' || projects.project_cost.id as cost_id, u.project_name as project_name , c.contact as contact_name,pc.project_code as projectCode from projects.project_cost LEFT JOIN projects.projects u on u.id = projects.project_cost.project LEFT JOIN projects.contacts c on c.id = projects.project_cost.contact left join PROJECTS.project_code pc on pc.id=projects.project_cost.project_code "+query+" order by id desc ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectCodeList/<id>', methods=['GET'])
def get_project_code_list(id):
    content = request.get_json(silent=True)
    finalResponse = []
    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.project_code.user_id="+str(id)+" or projects.project_code.user_id="+str(
            inviteUserId)+" and projects.project_code.project = ANY(Array"+str(projectArr)+")"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.project_code.user_id =" + \
                str(id)+" or projects.project_code.project = ANY(Array" + \
                str(projectUserList)+")"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.project_code.user_id ="+str(id)
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.project_code.*,projects.projects.project_name,CASE WHEN projects.project_code.cost_item='true' THEN 'Yes' ELSE 'No'  END as costItem,CASE WHEN projects.project_code.time_item='true' THEN 'Yes' ELSE 'No'  END as timeItem from projects.project_code left join projects.projects on projects.project_code.project = projects.projects.id "+query+" order by id desc ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getReleaseList/<userId>', methods=['GET'])
def get_release_list(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(" select projects.releases.*, (select count(*) from projects.features where version = projects.releases.id) as feature_count, projects.apps.app_name, (SELECT array_agg(u.project_name) as project_name FROM unnest(projects.releases.project) project LEFT JOIN projects.projects u on u.id = project), (SELECT array_agg(u.collection) as collection_name FROM unnest(projects.releases.related_collection) col LEFT JOIN projects.collections u on u.id = col) from projects.releases left join projects.apps on projects.releases.app = projects.apps.id where projects.releases.user_id ="+userId+" order by planned")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getFeatureList/<userId>', methods=['GET'])
def get_feature_list(userId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.features.*, projects.feature_status.name as status_name ,projects.releases.version as version_name, projects.apps.app_name from projects.features left join projects.apps on projects.features.app = projects.apps.id left join projects.feature_status on projects.features.status = projects.feature_status.id left join projects.releases on projects.features.version= projects.releases.id where projects.features.user_id ="+userId+"  order by id desc ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getFeatureListFilter/<userId>/<releaseId>', methods=['GET'])
def get_feature_list_filter(userId, releaseId):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.features.*, projects.feature_status.name as status_name ,projects.releases.version as version_name, projects.apps.app_name from projects.features left join projects.apps on projects.features.app = projects.apps.id left join projects.feature_status on projects.features.status = projects.feature_status.id left join projects.releases on projects.features.version= projects.releases.id where projects.features.user_id ="+userId+" and projects.features.version='"+releaseId+"'  order by id desc ")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTimeById/<id>', methods=['GET'])
def get_time_by_id(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.time where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectCostById/<id>', methods=['GET'])
def get_project_cost_by_id(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.project_cost where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getProjectCodeById/<id>', methods=['GET'])
def get_project_code_by_id(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.project_code where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getReleaseById/<id>', methods=['GET'])
def get_release_by_id(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.releases where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getFeatureById/<id>', methods=['GET'])
def get_feature_by_id(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from projects.features where id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addTime/<userId>', methods=['POST'])
def add_time(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.time (date_from, time, time_to, total_time, team_member, project, items, project_code, time_notes,user_id) values( NULLIF(%s, \'\')::date, NULLIF(%s, \'\')::time, NULLIF(%s, \'\')::time, %s, %s, %s,%s,%s,%s,%s) returning id',
                                                  (content.get('date_from'), content.get('time'), content.get('time_to'), content.get('total_time'), content.get('team_member'), content.get('project'), content.get('items'), content.get('project_code'), content.get('time_notes'), userId))
    id = rows[0][0]
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/updateTime/<id>', methods=['PUT'])
def update_time(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.time set date_from = NULLIF(%s, \'\')::date, time = NULLIF(%s, \'\')::time, time_to = NULLIF(%s, \'\')::time, total_time = %s, team_member=%s, project=%s, items=%s, project_code=%s, time_notes=%s where id=%s',
                                                           (content.get('date_from'), content.get('time'), content.get('time_to'), content.get('total_time'), content.get('team_member'), content.get('project'), content.get('items'), content.get('project_code'), content.get('time_notes'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addProjectCost/<userId>', methods=['POST'])
def add_project_cost(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.project_cost (date_from,user_id,project,activity,contact,project_code,description,reference,amount) values( NULLIF(%s, \'\')::date,%s,%s,%s,%s,%s,%s,%s,%s)',
                                                  (content.get('date_from'), userId, content.get('project'), content.get('activity'), content.get('contact'), content.get('projectCode'), content.get('description'), content.get('reference'), content.get('amount')))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateProjectCost/<id>', methods=['PUT'])
def update_project_cost(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.project_cost set date_from = NULLIF(%s, \'\')::date, project=%s, activity=%s, contact=%s,project_code=%s, description=%s, reference=%s, amount=%s where id=%s',
                                                           (content.get('date_from'), content.get('project'), content.get('activity'), content.get('contact'), content.get('projectCode'), content.get('description'), content.get('reference'), content.get('amount'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addProjectCode/<userId>', methods=['POST'])
def add_project_code(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.project_code (project_code,cost_item,time_item,description,project,user_id) values(%s,%s,%s,%s,%s,%s)',
                                                  (content.get('projectCode'), content.get('costItem'), content.get('timeItem'), content.get('description'), content.get('project'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateProjectCode/<id>', methods=['PUT'])
def update_project_code(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.project_code set project_code=%s, cost_item=%s, time_item=%s,description=%s, project=%s where id=%s',
                                                           (content.get('projectCode'), content.get('costItem'), content.get('timeItem'), content.get('description'), content.get('project'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addFeature/<userId>', methods=['POST'])
def add_features(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.features (app, version, feature_description, feature_title, planned, release_date, status, user_id) values(%s,%s,%s,%s, NULLIF(%s, \'\')::date, NULLIF(%s, \'\')::date,%s,%s) returning id',
                                                  (content.get('app'), content.get('version'), content.get('feature_description'), content.get('feature_title'), content.get('planned'), content.get('release_date'), content.get('status'), userId))
    id = rows[0][0]
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/updateFeature/<id>', methods=['PUT'])
def update_features(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.features set app=%s, version=%s, feature_description=%s, feature_title=%s, planned = NULLIF(%s, \'\')::date, release_date = NULLIF(%s, \'\')::date, status=%s where id=%s',
                                                           (content.get('app'), content.get('version'), content.get('feature_description'), content.get('feature_title'), content.get('planned'), content.get('release_date'), content.get('status'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/addRelease/<userId>', methods=['POST'])
def add_release(userId):
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.releases (app, version, planned, release_date, related_collection, project, info, user_id) values(%s,%s, NULLIF(%s, \'\')::date, NULLIF(%s, \'\')::date,%s,%s,%s,%s)',
                                                  (content.get('app'), content.get('version'), content.get('planned'), content.get('release_date'), content.get('related_collection'), content.get('project'), content.get('info'), userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateRelease/<id>', methods=['PUT'])
def update_release(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate('update PROJECTS.releases set app=%s, version=%s, planned = NULLIF(%s, \'\')::date, release_date = NULLIF(%s, \'\')::date, related_collection=%s, project=%s, info=%s where id=%s',
                                                           (content.get('app'), content.get('version'), content.get('planned'), content.get('release_date'), content.get('related_collection'), content.get('project'), content.get('info'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteTime/<id>', methods=['DELETE'])
def delete_time(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.time WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteProjectCost/<id>', methods=['DELETE'])
def delete_project_cost(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.project_cost WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteProjectCode/<id>', methods=['DELETE'])
def delete_project_code(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.project_code WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteFeature/<id>', methods=['DELETE'])
def delete_feature(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.features WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteRelease/<id>', methods=['DELETE'])
def delete_release(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM projects.releases WHERE id ="+id)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/checkFeatureVersionValidation/<version>/<app>', methods=['GET'])
def checkFeatureVersionValidation(version, app):
    rows = []
    rows = SQLHelpers.getInstance().executeQuery(
        "select id from projects.features where app ="+str(app)+" and version ='"+str(version)+"'")
    exist = None
    if len(rows) > 0:
        exist = True
    else:
        exist = False
    return jsonify({'code': "200", 'message': "success", "exist": exist})


@endpointV2.route('/v2/getMultipleProjectCollection', methods=['POST'])
def get_multiple_project_collection():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id as value, collection as label from projects.collections where projects && Array"+str(content.get('projects')))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")

# @endpointV2.route('/v2/getMultipleItemId', methods=['POST'])


def get_multiple_item_id(value):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select array_agg(item_id) from projects.items where id = Any(Array"+str(value)+")")
    return finalResponse


@endpointV2.route('/v2/getEpicItemsList/<id>', methods=['GET'])
def getEpicItemsList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id , item_id as name, description from projects.items where type = '5' and project = "+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getStatusDetailsList/<id>', methods=['GET'])
def getStatusDetailsList(id):
    finalResponse = []

    rows = SQLHelpers.getInstance().executeRawResult(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.statuslist.user_id="+str(id)+" or projects.statuslist.users="+str(
            id)+" or projects.statuslist.projects && (select array_agg(id) from projects.projects where created_by ='"+str(id)+"')"
    else:
        rows = SQLHelpers.getInstance().executeRawResult(
            'select type, username from projects.users where id ='+id)
        userType = rows[0][0]
        username = rows[0][1]
        rows = SQLHelpers.getInstance().executeRawResult(
            "select project from projects.invite where email ='"+username+"'")
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.statuslist.user_id =" + \
                str(id)+" or projects.statuslist.users="+str(id) + \
                " or projects.statuslist.projects && (select array_agg(id) from projects.projects where created_by ='"+str(
                    id)+"')"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.statuslist.user_id =" + \
                str(id)+" or projects.statuslist.users="+str(id)
        else:
            query = ""

    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.status_details.*, projects.statuslist.status_id, projects.statuslist.from_date, projects.statuslist.to_date, projects.statuslist.projects, projects.status_status.name as status_name, projects.projects.project_name, projects.items.item_id from projects.status_details left join projects.statuslist on projects.status_details.status_id = projects.statuslist.id  left join projects.status_status on projects.status_details.status = projects.status_status.id left join projects.items on projects.status_details.item = projects.items.id left join projects.projects on projects.status_details.project = projects.projects.id "+str(query))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getReleaseVersionList/<id>', methods=['GET'])
def getReleaseVersionList(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select id, version from projects.releases where app ="+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getstatusDetailsbyId/<id>', methods=['GET'])
def get_status_details_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select * from PROJECTS.status_details where status_id ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/deleteStatusDetails/<id>', methods=['DELETE'])
def delete_status_details(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("DELETE FROM PROJECTS.Status_details WHERE id = '" + id + "'")
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/updateStatusDetails/<id>', methods=['PUT'])
def update_status_detail(id):
    content = request.get_json(silent=True)
    SQLHelpers.getInstance().executeUpdate('update PROJECTS.status_details set status=%s, project=%s, info=%s, description=%s, item=%s where id=%s',
                                           (content.get('status'), content.get('project'), content.get('info'), content.get('description'), content.get('item'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getReleaseDate/<id>', methods=['GET'])
def getReleaseDate(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select planned, release_date from projects.releases where id ="+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/setFeatureVideo/<id>', methods=['POST'])
def set_feature_video(id):
    content = request.form
    image = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "featureVideo/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            sFilename = scriptFile.filename
            attachment = sFilename[:sFilename.rindex(
                ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"featureVideo/", attachment))

    SQLHelpers.getInstance().executeUpdate(
        'update projects.features set video=%s where id = %s', (attachment, id))

    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemsByMultipleProjects', methods=['POST'])
def get_items_by_multiple_projects():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.items.id, projects.items.item_id, projects.items.description, projects.items.priority, projects.items.date, projects.items.due_date, projects.items.collection, projects.priority.name as priority_name, projects.status.name as status_name from projects.items left join projects.priority on projects.items.priority = projects.priority.id left join projects.status on projects.items.status = projects.status.id where projects.items.project = ANY(Array"+str(content.get('projects'))+") and projects.items.status = 1  order by collection")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getSearchListAssociateItems', methods=['POST'])
def getSearchListAssociateItems():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.items.id, projects.items.item_id, projects.items.description, projects.items.priority, projects.items.date, projects.items.due_date, projects.items.collection, projects.priority.name as priority_name from projects.items left join projects.priority on projects.items.priority = projects.priority.id where projects.items.project = ANY(Array" +
                                                          str(content.get('projects'))+") and projects.items.status = 1 and (projects.items.item_id ILIKE '%"+str(content.get('value'))+"%' or projects.items.description ILIKE '%"+str(content.get('value'))+"%')  order by collection")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllAppListByType/<id>', methods=['POST'])
def get_all_app_list_by_type(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select *,(SELECT array_agg(u.instance_id) as instance_name FROM unnest(projects.apps.instance) inst LEFT JOIN projects.instance u on u.id = inst), (SELECT array_agg(u.team) as member_name FROM unnest(projects.apps.team_member) tm LEFT JOIN projects.teams u on u.id = tm)  from PROJECTS.apps where user_id=" +
                                                          id+" and status = ANY(Array"+str(content.get('type'))+") order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getTeamMemberByTeams', methods=['POST'])
def get_team_members_by_team():
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select name, id from projects.team_members where team && Array"+str(content.get('team'))+" and active = 'true'")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsByCollectionId/<collectionId>/<hoursType>', methods=['GET'])
def get_items_by_collection_id(collectionId, hoursType):
    if hoursType != 'none':
        query = " and " + str(hoursType) + " != '' and " + str(hoursType) + \
            " != '0' and " + str(hoursType) + " is not null "
    else:
        query = ""
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select PROJECTS.items.id, PROJECTS.items.item_id, PROJECTS.items.estimate, PROJECTS.items.actual,   PROJECTS.items.created_on, PROJECTS.items.description, projects.priority.name as priority_name, PROJECTS.status.name as status_name, PROJECTS.status.id as status_id from PROJECTS.items left join projects.priority on projects.items.priority = projects.priority.id LEFT JOIN PROJECTS.status  on PROJECTS.items.status = PROJECTS.status.id where collection=" + str(collectionId) + query + " order by created_on desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")
    # finalResponse =  SQLHelpers.getInstance().executeQuery("select PROJECTS.items.id, PROJECTS.items.item_id,  PROJECTS.items.created_on, PROJECTS.items.description, projects.priority.name as priority_name, PROJECTS.status.name as status_name from PROJECTS.items left join projects.priority on projects.items.priority = projects.priority.id LEFT JOIN PROJECTS.status  on PROJECTS.items.status = PROJECTS.status.id where collection="+str(collectionId)+" order by created_on desc")
    # return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getFeatureStatusList', methods=['GET'])
def get_feature_status_list():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select * from projects.feature_status')
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllFeatureListByStatus/<id>', methods=['POST'])
def get_all_feature_list_by_status(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery("select projects.features.*, projects.feature_status.name as status_name ,projects.releases.version as version_name, projects.apps.app_name from projects.features left join projects.apps on projects.features.app = projects.apps.id left join projects.feature_status on projects.features.status = projects.feature_status.id left join projects.releases on projects.features.version= projects.releases.id where projects.features.user_id ="+id+" and projects.features.status = ANY(Array"+str(content.get('status'))+") order by id desc")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateTeamActive/<id>', methods=['PUT'])
def update_team_active(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate(
        'update PROJECTS.team_members set active=%s where id=%s', (content.get('active'), id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getItemsBlocked/<id>', methods=['GET'])
def get_items_blocked(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") and projects.items.blocked = 'true'"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id =" + \
                str(id) + " and projects.items.blocked = 'true'"
        else:
            query = "where projects.items.blocked = 'true'"

    cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.team_members u on u.id = tagtype), (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , pu1.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id  left join projects.users pu1 on projects.items.user_id = pu1.id  left join projects.collections on projects.items.collection = projects.collections.id  "+query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsBlockedByStatusId/<id><statusId>', methods=['GET'])
def get_items_blocked_by_status_id(id, statusId):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id ="+str(id)+" or projects.items.project = ANY(Array"+str(
                projectUserList)+") and projects.items.blocked = 'true' and  status='"+statusId+"'"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id =" + \
                str(id) + " and projects.items.blocked = 'true' and  status='"+statusId+"'"
        else:
            query = "where projects.items.blocked = 'true' and  status='"+statusId+"'"

    cur.execute("select projects.items.*,(SELECT array_agg(u.name) as assigneevalue FROM unnest(projects.items.assignee) tagType LEFT JOIN projects.team_members u on u.id = tagtype), (SELECT array_agg(u.color) as color FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype), (SELECT  array_agg(u.title) as tagTitle FROM unnest(projects.items.tagtype) tagType LEFT JOIN projects.tagtype u on u.id = tagtype) ,projects.collections.collection as collection_name , pu1.username, projects.item_tag.user_id as userid, projects.item_tag.date as tag_date,projects.projects.project_name, PROJECTS.priority.name as priority_name, projects.status.name as status_name, projects.type.type as type_name from projects.items left join projects.priority on projects.items.priority = PROJECTS.priority.id left join projects.status  on projects.items.status = PROJECTS.status.id left join projects.type  on projects.items.type = PROJECTS.type.id left join projects.item_tag on projects.items.id = projects.item_tag.item_id left join projects.projects on projects.items.project = projects.projects.id  left join projects.users pu1 on projects.items.user_id = pu1.id  left join projects.collections on projects.items.collection = projects.collections.id  "+query)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/uploadItemFile/<userId>', methods=['POST'])
def upload_item_file(userId):
    now = datetime.now()
    content = request.form
    head = []
    final = []
    response = []
    createdItems = []
    pArr = []
    prArr = []
    sArr = []
    tArr = []
    dArr = []
    aArr = []
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER'] +
             "uploadItemFile/").mkdir(parents=True, exist_ok=True)
        if scriptFile:
            sFilename = scriptFile.filename
            attachment = sFilename[:sFilename.rindex(
                ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
            scriptFile.save(os.path.join(
                app.config['UPLOAD_FOLDER']+"uploadItemFile/", attachment))
            filepath = os.path.join(
                app.config['UPLOAD_FOLDER']+"uploadItemFile/", attachment)
            fileName = attachment
            with open(filepath, newline='') as csvfile:
                spamreader = csv.reader(csvfile, delimiter=',', quotechar='|')
                for index, item in enumerate(spamreader):
                    if(index == 0):
                        head.append(item)
                    else:
                        finalRow = {}
                        row = []
                        row.append(item)
                        for ind, it in enumerate(row[0]):
                            finalRow[head[0][ind]] = it
                        final.append(finalRow)

    for index, item in enumerate(final):
        assign_count = 0

        if 'project' in item:
            rows = SQLHelpers.getInstance().executeRawResult(
                "select id from projects.projects where project_name = '" + str(item['project'])+"'")
            if len(rows) > 0:
                project = rows[0][0]
            else:
                project = None
        if 'priority' in item:
            rows = SQLHelpers.getInstance().executeRawResult(
                "select id from projects.priority where lower(name) = '" + str(item['priority'])+"'")
            if len(rows) > 0:
                priority = rows[0][0]
            else:
                priority = None
        if 'status' in item:
            rows = SQLHelpers.getInstance().executeRawResult(
                "select id from projects.status where lower(name) = '" + str(item['status'])+"'")
            if len(rows) > 0:
                status = rows[0][0]
            else:
                status = None
        if 'type' in item:
            rows = SQLHelpers.getInstance().executeRawResult(
                "select id from projects.type where lower(type) = '" + str(item['type'])+"'")
            if len(rows) > 0:
                type = rows[0][0]
            else:
                type = None
        if 'collection' in item and project != None:
            rows = SQLHelpers.getInstance().executeRawResult("select id from projects.collections where collection = '" +
                                                             str(item['collection'])+"' and "+str(project)+" = any(projects)")
            if len(rows) > 0:
                collection = rows[0][0]
                assign_count = 1
            else:
                collection = None

        assignee = None
        if 'assignee' in item and project != None:
            assigneeArr = []
            project_list = item['assignee'].split(",")
            li = []
            for i in project_list:
                rows = SQLHelpers.getInstance().executeRawResult(
                    "select id from projects.team_members where name = '"+str(i)+"'")
                if len(rows) > 0:
                    c_id = rows[0][0]
                    assigneeArr.append(int(c_id))

            if len(assigneeArr) > 0:
                assignee = assigneeArr

        epic = None
        if 'epic' in item and project != None:
            rows = SQLHelpers.getInstance().executeRawResult("select id  from projects.items where type = '5' and project = '" +
                                                             str(project)+"' and item_id = '"+str(item['epic'])+"'")
            if len(rows) > 0:
                epic = rows[0][0]

        if 'description' in item:
            if item['description'] == "" or item['description'] == None:
                description = None
            else:
                description = item['description']

        if 'estimate' in item:
            if item['estimate'] == "" or item['estimate'] == None:
                estimate = "0"
            else:
                estimate = item['estimate']

        if 'actual' in item:
            if item['actual'] == "" or item['actual'] == None:
                actual = "0"
            else:
                actual = item['actual']

        if 'blocked' in item:
            if item['blocked'] != "" and item['blocked'] != None:
                blocked = item['blocked']
            else:
                blocked = False

        if (project != None and priority != None and status != None and type != None and description != None and assignee != None):
            createdItems.append(index + 1)
            rows1 = SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.items (USER_ID, PROJECT, DATE, DESCRIPTION, PRIORITY, ESTIMATE, ASSIGNEE, STATUS, TYPE, CREATED_ON, COLLECTION, ACTUAL, title, topic, followup, update_count, assign_count, due_date, epic, ide, blocked) VALUES (%s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                                                           (userId, project, datetime.strptime(item['date'], '%d-%m-%Y'), description, priority, estimate, assignee, status, type, now.strftime("%m-%d-%Y %I:%M %p"), collection, actual, item["title"], item["topic"], datetime.strptime(item['follow_up'], '%d-%m-%Y'), "0", assign_count, item["due_date"], epic, item["ide"], blocked))
            id = rows1[0][0]
            count = None
            rows = SQLHelpers.getInstance().executeRawResult(
                'select item_count,prefix from projects.projects where id ='+str(project))
            count = rows[0][0]
            prefix = rows[0][1]
            item_id = prefix + "-" + str(count+1)
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.items SET ITEM_ID = %s WHERE id = %s', (item_id, id))
            SQLHelpers.getInstance().executeUpdate(
                'UPDATE projects.projects SET item_count = %s WHERE id = %s', (count+1, str(project)))
        else:
            if project == None:
                pArr.append(index + 1)
            elif priority == None:
                prArr.append(index + 1)
            elif status == None:
                sArr.append(index + 1)
            elif type == None:
                tArr.append(index + 1)
            elif description == None:
                dArr.append(index + 1)
            elif assignee == None:
                aArr.append(index + 1)

    status = "Fail"
    if len(createdItems) > 0:
        response.append(
            {"items": createdItems, "response": "Item added successfully", "status": "Imported"})
        status = "Success"
    if len(pArr) > 0:
        response.append(
            {"items": pArr, "response": "Project provided not correct", "status": "Not Imported"})
    if len(prArr) > 0:
        response.append(
            {"items": prArr, "response": "Priority provided not correct", "status": "Not Imported"})
    if len(sArr) > 0:
        response.append(
            {"items": sArr, "response": "Status provided not correct", "status": "Not Imported"})
    if len(tArr) > 0:
        response.append(
            {"items": tArr, "response": "Type provided not correct", "status": "Not Imported"})
    if len(dArr) > 0:
        response.append(
            {"items": dArr, "response": "Description provided not correct", "status": "Not Imported"})
    if len(aArr) > 0:
        response.append(
            {"items": aArr, "response": "Assignee provided not correct", "status": "Not Imported"})

    json_object = json.dumps(response, indent=4)
    row = SQLHelpers.getInstance().executeUpdate("Insert into PROJECTS.imported_items (date, user_id, file_name, response, status) values(%s,%s,%s,%s,%s) returning id",
                                                 (now.strftime("%m-%d-%Y %I:%M %p"), userId, fileName, json_object, status))
    id = row[0][0]
    return jsonify({'code': "200", 'message': "success", "final": response, "id": id})


@endpointV2.route('/v2/getItemsUploadHistory/<userId>', methods=['GET'])
def get_items_upload_history(userId):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select i.*, u.name as user_name from projects.imported_items i left join projects.users u on i.user_id = u.id where i.user_id = '+str(userId)+' order by i.id desc')
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemsUploadById/<id>', methods=['GET'])
def get_items_upload_by_id(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select i.*, u.name as user_name from projects.imported_items i left join projects.users u on i.user_id = u.id where i.id = '+str(id))
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllItemsNotesView/<id>', methods=['GET'])
def get_items_notes_view(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") and (comment = '') is not true"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" and (comment = '') is not true"
        else:
            query = " where (comment = '') is not true"

    cur.execute("select projects.items_attachment.*, projects.collections.collection as collection_name, projects.items.item_id, projects.items.collection,  projects.projects.project_name, projects.users.username from projects.items_attachment left join projects.items on projects.items_attachment.items_id = projects.items.id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id "+query+" order by projects.items_attachment.id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getAllItemsAttachmentView/<id>', methods=['GET'])
def get_items_attachment_view(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute(
        'select invite_by,project from projects.user_project_mapping where user_id ='+id)
    rows = cur.fetchall()
    if len(rows) > 0:
        inviteUserId = rows[0][0]
        projectArr = rows[0][1]
        query = "WHERE projects.items.user_id="+str(id)+" or projects.items.user_id="+str(
            inviteUserId)+" and projects.items.project = ANY(Array"+str(projectArr)+")"
    else:
        cur.execute('select type, username from projects.users where id ='+id)
        rows = cur.fetchall()
        userType = rows[0][0]
        username = rows[0][1]
        cur.execute(
            "select project from projects.invite where email ='"+username+"'")
        rows = cur.fetchall()
        pInvite = False
        if len(rows) > 0:
            projectUserList = rows[0][0]
            pInvite = True
        if userType == "I" and pInvite == True:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" or projects.items.project = ANY(Array" + \
                str(projectUserList)+") and (attachment = '') is not true"
        elif userType == "I" and pInvite == False:
            query = "WHERE projects.items.user_id =" + \
                str(id)+" and (attachment = '') is not true"
        else:
            query = " where (attachment = '') is not true"

    cur.execute("select projects.items_attachment.*, projects.items.item_id, projects.items.collection , projects.collections.collection as collection_name , projects.projects.project_name, projects.users.username from projects.items_attachment left join projects.items on projects.items_attachment.items_id = projects.items.id left join projects.projects on projects.items.project = projects.projects.id left join projects.users on projects.items.user_id = projects.users.id left join projects.collections on projects.items.collection = projects.collections.id "+query + " order by projects.items_attachment.id desc")
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


def generateOTP(num):
    digits = "0123456789"
    OTP = ""

    for i in range(num):
        OTP += digits[math.floor(random.random() * 10)]

    return OTP


@endpointV2.route('/v2/otpConfirmationEmail/<email>/<name>', methods=['GET'])
def otp_confirmation_email(email, name):
    msg = Message(
        "Otp for Istoria",
        sender=('Istoria Team', mailSender),
        recipients=[email]
    )

    random = generateOTP(6)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("Insert into PROJECTS.otp (otp) values('" +
                str(random)+"') returning id")
    rows = cur.fetchall()
    # rows = SQLHelpers.getInstance().executeRawResult("Insert into PROJECTS.otp (otp) values('"+str(random)+"') returning id")
    id = rows[0][0]
    body = "Dear " + name+",\n\n"+random + \
        " is your Onetime password (OTP) for your Istoria account.\n\nHave a great day!\n\nBest Regards,\nThe Istoria Team"
    msg.body = body
    mail.send(msg)
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success", "id": id})


@endpointV2.route('/v2/getOtp/<id>/<otp>', methods=['GET'])
def getOtp(id, otp):
    rows = SQLHelpers.getInstance().executeRawResult(
        'select otp from projects.otp where id = '+str(id))
    resp = False
    if len(rows) > 0:
        otp1 = rows[0][0]
        if otp == otp1:
            resp = True

    return jsonify({'code': "200", 'message': "success", "toggle": resp})


@endpointV2.route('/v2/getAppTypes/', methods=['GET'])
def get_AppTypes():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "SELECT id as value, type_name as label from PROJECTS.APP_TYPE")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateDeclineInvite/<id>', methods=['PUT'])
def update_decline_invite(id):
    content = request.get_json(silent=True)
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeUpdate(
        'update PROJECTS.invite set accepted=%s where id=%s', ("Cancelled", id))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setTimeAttachment/<id>', methods=['POST'])
def set_time_attachment(id):
    now = datetime.now()
    content = request.get_json(silent=True)
    userId = content.get("userId")
    if (content.get("tempAttachment") is not None and len(content.get("tempAttachment")) > 0):
        for fileAttach in content.get("tempAttachment"):
            try:
                Path(app.config['UPLOAD_FOLDER']+"attachments/" +
                     str(id)+"/").mkdir(parents=True, exist_ok=True)
                shutil.move(app.config['UPLOAD_FOLDER']+"temp/"+userId+"/"+fileAttach,
                            app.config['UPLOAD_FOLDER']+"attachments/"+str(userId)+"/"+fileAttach)
                SQLHelpers.getInstance().executeUpdate('INSERT INTO projects.time_attachment (time_id, ATTACHMENT, DATE, USER_BY) VALUES (%s, %s, %s,%s )',
                                                       (str(id), fileAttach, now, content.get("userId")))
            except Exception as ex:
                app.logger.info(
                    "Error in moving temporary attachments: %s", traceback.format_exc())
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/setTimeUpdateAttachment/<id>/<userId>', methods=['POST'])
def set_time_update_attachment(id, userId):
    now = datetime.now()
    attachment = None
    if 'file' in request.files:
        scriptFile = request.files['file']
        Path(app.config['UPLOAD_FOLDER']+"attachments/" +
             userId+"/").mkdir(parents=True, exist_ok=True)

        if scriptFile:
            allFiles = request.files.getlist("file")
            # app.logger.info("multiple file attachment:: %s", allFiles)
            for sFile in allFiles:
                sFilename = sFile.filename
                attachment = sFilename[:sFilename.rindex(
                    ".")]+"_"+str(randint(100, 9999999))+sFilename[sFilename.rindex("."):]
                # app.logger.info("attachment file name:: %s", attachment)
                sFile.save(os.path.join(
                    app.config['UPLOAD_FOLDER']+"attachments/"+str(userId)+"/", attachment))
                # attachments.append(attachment)
                SQLHelpers.getInstance().executeUpdate(
                    'INSERT INTO projects.time_attachment (time_id, ATTACHMENT, DATE, USER_BY) VALUES (%s, %s, %s,%s )', (str(id), attachment, now, userId))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getTimeAttachment/<id>', methods=['GET'])
def get_time_attachment(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        'select id, attachment from PROJECTS.TIME_ATTACHMENT ta WHERE  ta.time_id= ' + id + ' order by ta.date desc')
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/downloadTimeAttachment/<id>/<fileName>', methods=['GET'])
def download_time_Attachment(id, fileName):
    return send_from_directory(directory=app.config['UPLOAD_FOLDER']+"attachments/"+str(id)+"/", filename=fileName)


@endpointV2.route('/v2/deleteTimeAttachment/<id>', methods=['DELETE'])
def delete_time_attachment(id):
    SQLHelpers.getInstance().executeUpdate(
        "DELETE FROM projects.time_attachment WHERE id = '" + id + "'")
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getToolsList/<id>', methods=['GET'])
def get_tools_list(id):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "select projects.tools.*, projects.users.username from projects.tools left join projects.users on projects.tools.created_by = projects.users.id where created_by ="+id)
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/addTools/<userID>', methods=['POST'])
def add_tools(userID):
    now = datetime.now()
    content = request.get_json(silent=True)
    rows = SQLHelpers.getInstance().executeUpdate('Insert into PROJECTS.tools (product, supplier, version, instance, usage,url, comments, created_on, created_by) values(%s,%s,%s,%s,%s,%s,%s,%s,%s)', (content.get(
        'product'), content.get('supplier'), content.get('version'),  content.get('instance'), content.get('usage'), content.get('url'), content.get('comments'), now.strftime("%m-%d-%Y %I:%M %p"), userID))
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/deleteTools/<id>', methods=['DELETE'])
def delete_tools(id):
    SQLHelpers.getInstance().executeUpdate(
        "DELETE FROM projects.tools WHERE id ="+id)
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getToolsById/<id>', methods=['GET'])
def get_tools_by_id(id):
    finalResponse = []
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute("select * from projects.tools where id ="+id)
    colnames = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    result = []
    for item1 in rows:
        columnValue = {}
        for index, item in enumerate(item1):
            columnValue[colnames[index]] = item
        finalResponse.append(columnValue)
    con.close()
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/updateTools/<id>', methods=['PUT'])
def update_tools(id):
    content = request.get_json(silent=True)
    configuration = AdminConfiguration.objects().first()
    con = psycopg2.connect(database=configuration.database, user=configuration.user,
                           password=configuration.password, host=configuration.host, port=configuration.port)
    cur = con.cursor()
    cur.execute('update projects.tools set product =%s, supplier =%s, version =%s, instance =%s, usage =%s,url =%s, comments =%s where id =%s', (content.get(
        'product'), content.get('supplier'), content.get('version'),  content.get('instance'), content.get('usage'), content.get('url'), content.get('comments'), id))
    con.commit()
    con.close()
    return jsonify({'code': "200", 'message': "success"})


@endpointV2.route('/v2/getCollectionDates/<colId>', methods=['GET'])
def get_collection_date(colId):
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "SELECT from_date, to_date from PROJECTS.collections where id= '"+str(colId)+"'")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")


@endpointV2.route('/v2/getItemDueDate', methods=['POST'])
def get_item_due_date():
    datetoggle = True
    content = request.get_json(silent=True)
    finalResponse = []
    for item in content.get('item'):
        rows = SQLHelpers.getInstance().executeRawResult(
            "SELECT due_date from PROJECTS.items where id= '"+str(item)+"'")
        if len(rows) > 0 and rows[0][0] != None:
            due_date = str(rows[0][0])
            d = due_date.split('-')
            d_date = d[0][2:4] + "/" + d[1] + "/" + d[2]
            if (content.get('from_date') < d_date and content.get('to_date') > d_date):
                pass
            else:
                datetoggle = False
    return jsonify({'code': "200", 'message': "success", "datetoggle": datetoggle})

@endpointV2.route('/v2/getEventType', methods=['GET'])
def get_event_type():
    finalResponse = []
    finalResponse = SQLHelpers.getInstance().executeQuery(
        "SELECT * from PROJECTS.event_types")
    return Response(response=dumps(finalResponse, indent=4, sort_keys=True, default=str), status=200, mimetype="application/json")