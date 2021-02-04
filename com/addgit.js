import React, { Component } from 'react';
import { Form, Button, Alert, Modal, InputGroup, FormControl } from 'react-bootstrap';
import { setGit, getProjectList, getGitById, updateGit,getRepos,getProviders,testConnectionGit,ValidateGitHubAccount,getGitHubRepo,setGithubRepo } from '../../util/APIUtils';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faSyncAlt } from '@fortawesome/free-solid-svg-icons';
import * as moment from 'moment';
import CustomLoader from '../customLoader';
import Select from 'react-select'
import makeAnimated from 'react-select/animated';
import { toast } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import 'test1' from 'react/test1';
const animatedComponents = makeAnimated();



class AddInstance extends Component {
    constructor(props) {
        super(props);
        this.state = {
            gitAccount: '',
            provider: '',
            monthly_cost: '',
            repos: '',
            projectList: [],
            project: [],
            dateTime: '',
            description:'',
            validated: false,
            repoValidated: false,
            loader: false,
            reposList:[],
            providerList:[],
            isGitHubSelected:false,
            isConnectionPass:false,
            id:'',
            userId: '',
            token: '',
            ownerName: '',
            repoName: '',
            repoStep:false,
            gitHubRepoList: [],
            selectedGitHubRepoList: [],
            mappedGitHubRepo:[],
            editToggle :false,
        }
        this.loaderStart = this.loaderStart.bind(this);
        this.loaderClose = this.loaderClose.bind(this);
    }

    componentDidMount() {
        if (this.props.editId != "") {
            this.setState({ loader: true, id: this.props.editId , editToggle :true});
            getGitById(this.props.editId).then(response => {
                console.log("getDomainById ==> ", response);
                if(response[0].provider=="1")
                {

                this.setState({ isGitHubSelected: true });
                
        console.log("this.state.repos::::::::::::::::: ",  response[0].repos) 
        
        if( response[0].repos!=undefined &&  response[0].repos!=null &&  response[0].repos!="" )
        {
            getRepos(localStorage.getItem("userId")).then(repoResponse => {
                this.setState({ reposList: repoResponse});
                var finalListRepo=[];
                console.log("this.state.reposList::::::::::::::::: ",  this.state.reposList) 
                this.state.reposList.forEach(function (item) {
                    if(response[0].repos.includes(item.id))
                    finalListRepo.push(item.repo_name);
                })
                this.setState({ mappedGitHubRepo: finalListRepo});
                console.log("mappedGitHubRepo::::::::::::::::: ",this.state.mappedGitHubRepo) 
            }).catch(error => {
                console.log("oops ! something went wrong !! ", error)
            });
        
    }
                }
                this.setState({
                    gitAccount: response[0].gitaccount,
                    project: response[0].project,
                    provider: response[0].provider,
                    ownerName: response[0].owner,
                    userId: response[0].userid,
                    token: response[0].token,
                    monthly_cost: response[0].monthly_cost,
                    repos: response[0].repos,
                    description:response[0].description,
                });
                
                
                this.props.removeId();
                this.setState({ loader: false });
            }).catch(error => {
                console.log("oops ! something went wrong !! ", error)
            });
        }
        this.getDateTime();
        this.getProjectDropdown();
        this.getRepoDropdown();
        this.getProviderDropdown();
        
               
                
    }

    loaderStart() {
        this.setState({ loader: true })
    }

    loaderClose() {
        this.setState({ loader: false })
    }

    getDateTime() {
        let tempDate = new Date();
        var y = moment().format("MM-DD-YYYY hh:mm A");
        this.setState({ dateTime: y });
    }
    getProjectDropdown() {
        var listA = [];
        var listB = [];
        var self = this;
        getProjectList(localStorage.getItem("userId")).then(response => {
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

    getRepoDropdown() {
        
        getRepos(localStorage.getItem("userId")).then(response => {
            this.setState({ reposList: response});
        }).catch(error => {
            console.log("oops ! something went wrong !! ", error)
        });

    }

    getProviderDropdown() {
        
        getProviders().then(response => {
            this.setState({ providerList: response});
        }).catch(error => {
            console.log("oops ! something went wrong !! ", error)
        });
    }

    validate(event,arg) {
      
        if (this.state.gitAccount == '' || this.state.gitAccount == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if (this.state.provider == '' || this.state.provider == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if ( this.state.isGitHubSelected && (this.state.ownerName == '' || this.state.ownerName == undefined)) {
            event.preventDefault();
            event.stopPropagation();
        } /*else if (this.state.isGitHubSelected && (this.state.userId == '' || this.state.userId == undefined)) {
            event.preventDefault();
            event.stopPropagation();
        }*/ else if (this.state.isGitHubSelected && (this.state.token == '' || this.state.token == undefined)) {
            event.preventDefault();
            event.stopPropagation();
        }
        else if (this.state.monthly_cost == '' || this.state.monthly_cost == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else if (!this.state.isGitHubSelected && (this.state.repos == '' || this.state.repos == undefined)) {
            event.preventDefault();
            event.stopPropagation();
        } else if (this.state.project == '' || this.state.project == undefined) {
            event.preventDefault();
            event.stopPropagation();
        } else {
            if(arg=="2")
        {
            this.testConnection(); 
        }
        else
        {
            this.addByApi();
        }
        }
        this.setState({ validated: true });
    
    }


    repoValidated(event,arg) {
      
        if (this.state.selectedGitHubRepoList.length<=0) {
            toast.error("Please select repository")
        }  else {
            if(arg=="2")
        {
            this.testConnection(); 
        }
        else
        {
            this.addRepoByApi();
        }
        }
        this.setState({ repoValidated: true });
    
    }
    cancelRepo(event,arg)
    {
        this.props.afterSubmitEmailModal("git");
    }


    addByApi() {
        var projectFinalList = [];
        var finalRepoList=[];
        this.setState({ loader: true });
        this.state.project.forEach(function (item) {
            projectFinalList.push(item.value);
        })
        if(this.state.repos!="" && this.state.repos!=undefined && this.state.repos!=null)
        {
            if(this.state.isGitHubSelected)
            {
            this.state.repos.forEach(function (item) {
            finalRepoList.push(item);
        })
            }
            else
            {
                finalRepoList.push(Number(this.state.repos));  
            }
       
        }
        
        const data = {
            gitAccount: this.state.gitAccount,
            provider: this.state.provider,
            owner: this.state.ownerName,
            userId: this.state.userId,
            token: this.state.token,
            monthly_cost: this.state.monthly_cost,
            repos: finalRepoList,
            project: projectFinalList,
            createdOn: this.state.dateTime,
            description:this.state.description,
        };
        if (this.state.id == "") {
            setGit(data, localStorage.getItem("userId")).then(response => {
                console.log("save git data ==>", response)
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                this.setState({ id: response.message });
                if(this.state.isGitHubSelected)
                {
                    getGitHubRepo(data).then(response => {
                        console.log("getGitHubRepo ==> ", response)
                        if (response.length>0) {
                           // toast.info("Connection Working Properly")
                            this.setState({ repoStep: true });
                            this.setState({ gitHubRepoList: response});
                        }
                        else {
                            toast.error("Unable to get repo list from github")
                            this.setState({ repoStep: false });
                        }
                        this.loaderClose();
                    }).catch(error => {
                        this.loaderClose();
                        console.log("Error Status =>", error)
                    });
                   
                }
                else
                {
                this.props.afterSubmitEmailModal("git");
                }
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
        } else {
            updateGit(data, this.state.id).then(response => {
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                if(this.state.isGitHubSelected)
                {
                    getGitHubRepo(data).then(response => {
                        console.log("getGitHubRepo ==> ", response)
                        if (response.length>0) {
                           // toast.info("Connection Working Properly")
                            this.setState({ repoStep: true });
                            this.setState({ gitHubRepoList: response});
                        }
                        else {
                            toast.error("Unable to get repo list from github")
                            this.setState({ repoStep: false });
                        }
                        this.loaderClose();
                    }).catch(error => {
                        this.loaderClose();
                        console.log("Error Status =>", error)
                    });
                   
                }
                else
                {
                this.props.afterSubmitEmailModal("git");
                }
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
        }
    }


    addRepoByApi() {
        var projectFinalList = [];
        this.setState({ loader: true });
        this.state.project.forEach(function (item) {
            projectFinalList.push(item.value);
        })
        
        const data = {
            gitAccount: this.state.gitAccount,
            repo_name: this.state.selectedGitHubRepoList.join(),
            stack: "",
            project: projectFinalList,
            createdOn: this.state.dateTime,
        };
       // if (this.state.id == "") {
        setGithubRepo(data, localStorage.getItem("userId"),this.state.id).then(response => {
                console.log("setGithubRepo data ==>", response)
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                this.props.afterSubmitEmailModal("gitWithRepo");
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
       /* } else {
            updateRepo(data, this.state.id).then(response => {
                this.setState({ showAlert: true })
                this.setState({ loader: false });
                this.props.afterSubmitEmailModal("git");
            }).catch(error => {
                console.log("oops ! something went wrong !! ")
            });
        }*/
    
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
    providerSelected=(value)=>
    {
        this.setState({ provider: value })
        if(value=="1")
        {
            this.setState({ isGitHubSelected: true })
        }
        else
        {
            this.setState({ isGitHubSelected: false })  
        }
    }
    repoSelected=(event)=>
    {
        this.setState({ repos: event.target.value })
        var index = event.nativeEvent.target.selectedIndex;
        this.setState({ repoName: event.nativeEvent.target[index].text })
    }
    testConnection() {
       
        
        this.loaderStart();
        const data = {
            "owner": this.state.ownerName,
            "repo": this.state.repoName,
            "userId": this.state.userId,
            "token": this.state.token
        };
        ValidateGitHubAccount(data).then(response => {
            console.log("testConnectionGit ==> ", response.status)
            if (response.status == 200) {
                toast.info("Token successfully verify.")
                this.setState({ isConnectionPass: true })
            }
            else {
                toast.error("Git token is invalid")
                this.setState({ isConnectionPass: false })
            }
            this.loaderClose();
        }).catch(error => {
            this.loaderClose();
            console.log("Error Status =>", error)
        });
    
    }

    onAddingItem = (i,cb) => (event) => {
        var repoFinalList = [];
        console.log("checkbox "+i);
        console.log("checked event:::::::",event.target.checked)
        if(event.target.checked)
        {
            console.log("checked repo details",this.state.gitHubRepoList[i]);
            this.state.selectedGitHubRepoList.push(this.state.gitHubRepoList[i].name);
        }
        else{
            this.state.selectedGitHubRepoList.splice(0,i);
        }
        console.log("final selected repo "+this.state.selectedGitHubRepoList);
       /* this.state.gitHubRepoList.forEach(function (item) {

            projectFinalList.push(item.value);
        })*/
      }

    render() {
        const { validated,repoValidated, showAlert, showAlertFailed } = this.state;
        return (
            <div>
                <Modal.Header closeButton>
                <Modal.Title>{!this.state.editToggle ? "Add Git Details" : "Edit Git Details"}</Modal.Title>
                </Modal.Header>
                <Modal.Body style={{ minHeight: "80vh" }}>
                {!this.state.repoStep? 
                 <Form noValidate validated={validated} action="#" className="p-3">
                        <Form.Group controlId="validationfirstName">
                            <Form.Label>Git Account</Form.Label>
                            <Form.Control type="text" name="gitAccount"
                                autoComplete="off"
                                onKeyDown={this.handleKeyDown}
                                value={this.state.gitAccount}
                                onChange={(event) => { this.setState({ gitAccount: event.target.value }) }}
                                className="form-control" required />
                            <Form.Control.Feedback type="invalid" >Please enter git account.</Form.Control.Feedback>
                        </Form.Group>
                        <Form.Group controlId="validationfirstName" className="mb-2">
                            <Form.Label>Provider</Form.Label>
                            <Form.Control as="select" name="provider"
                                autoComplete="off"
                                value={this.state.provider}
                                onChange={(event) => { this.providerSelected(event.target.value) }}
                                className="form-control"
                                required>
                                <option value="">Select</option>
                                {this.state.providerList.map(item => (
                                    <option value={item.id}>{item.name}</option>
                                ))}
                            </Form.Control>
                            <Form.Control.Feedback type="invalid" >Please select provider</Form.Control.Feedback>
                            </Form.Group>
                            {this.state.isGitHubSelected? <React.Fragment>
                                {/*
                            <Form.Group controlId="validationpassword">
                                <Form.Label>User Id</Form.Label>
                                <Form.Control type="text" name="userId"
                                    autoComplete="off"
                                    value={this.state.userId}
                                    onChange={(event) => { this.setState({ userId: event.target.value }) }}
                                    className="form-control"
                                    required
                                />
                                <Form.Control.Feedback type="invalid" >Please enter user id</Form.Control.Feedback>
                                
                            </Form.Group>
                            */}
                            <Form.Group controlId="validationpassword">
                                <Form.Label>Token</Form.Label>
                                <Form.Control type="text" name="token"
                                    autoComplete="off"
                                    value={this.state.token}
                                    onChange={(event) => { this.setState({ token: event.target.value }) }}
                                    className="form-control"
                                    required
                                />
                                <Form.Control.Feedback type="invalid" >Please enter token</Form.Control.Feedback>
                            </Form.Group>
                            <Form.Group controlId="validationpassword">
                                <Form.Label>Owner Name</Form.Label>
                                <Form.Control type="text" name="ownerName"
                                    autoComplete="off"
                                    value={this.state.ownerName}
                                    onChange={(event) => { this.setState({ ownerName: event.target.value }) }}
                                    className="form-control"
                                    required
                                />
                                <Form.Control.Feedback type="invalid" >Please enter owner name</Form.Control.Feedback>
                            </Form.Group></React.Fragment>:false}
                        <Form.Group controlId="validationfirstName">
                            <Form.Label>Monthly Cost</Form.Label>
                            <Form.Control type="text" name="monthly_cost"
                                autoComplete="off"
                                onKeyDown={this.handleKeyDown}
                                value={this.state.monthly_cost}
                                onChange={(event) => { this.setState({ monthly_cost: event.target.value }) }}
                                className="form-control" required />
                            <Form.Control.Feedback type="invalid" >Please enter monthly cost.</Form.Control.Feedback>
                        </Form.Group>
                        {!this.state.isGitHubSelected? <React.Fragment>
                        <Form.Group controlId="validationfirstName" className="mb-2">
                            <Form.Label>Repos</Form.Label>
                            <Form.Control as="select" name="repos"
                                autoComplete="off"
                                value={this.state.repos}
                                onChange={(event) => { this.repoSelected(event) }}
                                className="form-control"
                                required>
                                <option value="">Select</option>
                                {this.state.reposList.map(item => (
                                    <option value={item.id}>{item.repo_name}</option>
                                ))}
                            </Form.Control>
                            
                            <Form.Control.Feedback type="invalid" >Please select repos</Form.Control.Feedback>
                        </Form.Group></React.Fragment>:false}
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

                        <Form.Group controlId="validationpassword" className="mb-2">
                            <Form.Label>Notes</Form.Label>
                            <Form.Control as="textarea" name="description"
                                autoComplete="off"
                                rows="4"
                                onChange={(event) => { this.setState({ description: event.target.value }) }}
                                className="form-control"
                                value={this.state.description}
                                
                            />
                            <Form.Control.Feedback type="invalid" >Please enter notes</Form.Control.Feedback>
                        </Form.Group>

                        {!this.state.isGitHubSelected?<div className="text-center">
                            <button type="button" className="btn btn-primary my-2" onClick={(e) => this.validate(e,"1")}>Submit</button>
                        </div>:""}
                        {this.state.isGitHubSelected?<div className="text-center">
                        {this.state.isConnectionPass? <button type="button" className="btn btn-primary my-2 mx-0 mx-lg-2" onClick={(e) => this.validate(e,"1")}>Submit</button>:""}
                        {!this.state.isConnectionPass?<button type="button" className="btn btn-primary my-2 mx-0 mx-lg-2" onClick={(e) => this.validate(e,"2")}>Test Connection</button>:""}
                        </div>:""}
                    </Form>:false}
                    {this.state.repoStep? 
                   <Form noValidate validated={repoValidated} action="#" className="p-3">
                       <div >
                       Please select repository .
                        </div>
                   <hr/>
                   <div>
                        { this.state.gitHubRepoList.map((repo, i) =>{
                                 return(
                           
                                    this.state.mappedGitHubRepo.includes(repo.name)?<Form.Group controlId={i+1} className="pattern-search mb-0">
                             <Form.Check type="switch" size="lg">
                                 <Form.Check.Input type="checkbox" value={repo.name} checked={true} />
                                 <Form.Check.Label className="chkb-label">{repo.name}</Form.Check.Label>
                             </Form.Check>
                         </Form.Group>:
                         <Form.Group controlId={i+1} className="pattern-search mb-0">
                         <Form.Check type="switch" size="lg">
                             <Form.Check.Input type="checkbox" value={repo.name}  onChange={this.onAddingItem(i)} />
                             <Form.Check.Label className="chkb-label">{repo.name}</Form.Check.Label>
                         </Form.Check>
                         
                     </Form.Group>
                     
                                 )
                        })}
                        <hr/>
                     </div>
                        <div className="text-center">
                        <button type="button" className="btn btn-primary my-2 mx-0 mx-lg-2" onClick={(e) => this.repoValidated(e,"1")}>Submit</button>
                        <button type="button" className="btn btn-primary my-2 mx-0 mx-lg-2" onClick={(e) => this.cancelRepo(e,"1")}>Cancel</button>
                        </div>
                        </Form>  :false}
                        
                </Modal.Body>
                {this.state.loader ? <CustomLoader /> : false}
            </div>
        )
    }

}
export default AddInstance;
