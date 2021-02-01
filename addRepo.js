import React, { Component } from 'react';
import { Form, Button, Alert, Modal, InputGroup, FormControl } from 'react-bootstrap';
import { setRepo, getInviteProjectList, getRepoById, updateRepo } from '../../util/APIUtils';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faSyncAlt } from '@fortawesome/free-solid-svg-icons';
import * as moment from 'moment'
import CustomLoader from '../customLoader';
import Select from 'react-select'
import makeAnimated from 'react-select/animated';


const animatedComponents = makeAnimated();

class AddRepo extends Component {
    constructor(props) {
        super(props);
        this.state = {
            gitAccount: '',
            repo_name: '',
            stack: '',
            projectList: [],
            project: [],
            dateTime: '',
            validated: false,
            loader: false,
            id:'',
            editToggle :false,
        }
    }

    componentDidMount() {
        if (this.props.editId != "") {
            this.setState({ loader: true, id: this.props.editId , editToggle :true});
            getRepoById(this.props.editId).then(response => {
                console.log("getDomainById ==> ", response);
                this.setState({
                    gitAccount: response[0].gitaccount,
                    project: response[0].project,
                    repo_name: response[0].repo_name,
                    stack: response[0].stack,
                });
                this.props.removeId();
                this.setState({ loader: false });
            }).catch(error => {
                console.log("oops ! something went wrong !! ", error)
            });
        }
        this.getDateTime();
        this.getProjectDropdown();
    }
    getProjectDropdown() {
        var listA = [];
        var listB = [];
        var self = this;
        getInviteProjectList(localStorage.getItem("userId")).then(response => {
            response.forEach(function (item) {
                listA.push({ value: item.id, label: item.project_name });
                if (self.state.project.includes(item.id)) {
                    listB.push({ value: item.id, label: item.project_name });
                }
            });
            this.setState({ projectList: listA, project: listB });
        }).catch(error => {
            console.log("oops ! something went wrong !! ", error)
        });
    }
    getDateTime() {
        let tempDate = new Date();
        var y = moment().format("MM-DD-YYYY hh:mm A");
        this.setState({ dateTime: y });
    }
    validate() {
        if (this.state.gitAccount == '' || this.state.gitAccount == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if (this.state.repo_name == '' || this.state.repo_name == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if (this.state.stack == '' || this.state.stack == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if (this.state.project == '' || this.state.project == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else {
            this.addByApi();
        }
        this.setState({ validated: true });
    }


    addByApi() {
        var projectFinalList = [];
        this.setState({ loader: true });
        this.state.project.forEach(function (item) {
            projectFinalList.push(item.value);
        })
        const data = {
            gitAccount: this.state.gitAccount,
            repo_name: this.state.repo_name,
            stack: this.state.stack,
            project: projectFinalList,
            createdOn: this.state.dateTime,
        };
        if (this.state.id == "") {
            setRepo(data, localStorage.getItem("userId")).then(response => {
                console.log("data ==>", response)
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                this.props.afterSubmitEmailModal("repo");
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
        } else {
            updateRepo(data, this.state.id).then(response => {
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                this.props.afterSubmitEmailModal("repo");
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
        }
    }

    handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            this.validate(e);
        }
    }

    handleChange = (selectedOptions) => {
        this.setState({ project: selectedOptions });
        console.log("handle change ==>  ", this.state.project)
    }

    render() {
        const { validated, showAlert, showAlertFailed } = this.state;
        return (
            <div>
                <Modal.Header closeButton>
                <Modal.Title>{!this.state.editToggle ? "Add Repo" : "Edit Repo"}</Modal.Title>
                </Modal.Header>
                <Modal.Body style={{ minHeight: "80vh" }}>
                    <Form noValidate validated={validated} action="#" className="p-3">
                        <Form.Group controlId="validationfirstName">
                            <Form.Label>Git Account</Form.Label>
                            <Form.Control type="text" name="gitAccount"
                                autoComplete="off"
                                readOnly={true}
                                onKeyDown={this.handleKeyDown}
                                value={this.state.gitAccount}
                                onChange={(event) => { this.setState({ gitAccount: event.target.value }) }}
                                className="form-control" required />
                            <Form.Control.Feedback type="invalid" >Please enter git account.</Form.Control.Feedback>
                        </Form.Group>
                        <Form.Group controlId="validationpassword">
                            <Form.Label>Repo Name</Form.Label>
                            <Form.Control type="text" name="repo_name"
                                autoComplete="off"
                                readOnly={true}
                                onChange={(event) => { this.setState({ repo_name: event.target.value }) }}
                                className="form-control"
                                value={this.state.repo_name}
                                onKeyDown={this.handleKeyDown}
                                required
                            />
                            <Form.Control.Feedback type="invalid" >Please enter repo name.</Form.Control.Feedback>
                        </Form.Group>
                        <Form.Group controlId="validationfirstName">
                            <Form.Label>Stack</Form.Label>
                            <Form.Control type="text" name="stack"
                                autoComplete="off"
                                onKeyDown={this.handleKeyDown}
                                value={this.state.stack}
                                onChange={(event) => { this.setState({ stack: event.target.value }) }}
                                className="form-control" required />
                            <Form.Control.Feedback type="invalid" >Please enter stack.</Form.Control.Feedback>
                        </Form.Group>
                        <Form.Group controlId="validationpassword">
                            <Form.Label>Projects Used</Form.Label>
                            <Select
                                closeMenuOnSelect={false}
                                components={animatedComponents}
                                isMulti
                                value={this.state.project}
                                options={this.state.projectList}
                                onChange={this.handleChange}
                            />
                            <Form.Control.Feedback type="invalid" >Please select project </Form.Control.Feedback>
                        </Form.Group>
                        <div className="text-center">
                            <button type="button" className="btn btn-primary my-2" onClick={(e) => this.validate(e)}>Submit</button>
                        </div>
                    </Form>
                </Modal.Body>
                {this.state.loader ? <CustomLoader /> : false}
            </div>
        )
    }

}
export default AddRepo;
