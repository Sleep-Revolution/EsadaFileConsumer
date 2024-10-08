import os
os.environ["OMP_NUM_THREADS"]="1"
import numpy as np
from statsmodels.stats.inter_rater import aggregate_raters
import sklearn.cluster as skc
from scipy.stats import multinomial,dirichlet
from scipy.optimize import minimize
import pandas as pd
from sklearn.preprocessing import OneHotEncoder
import pickle

"""
####################################################################################
##########################                                ##########################
##########################         Mixture Models         ##########################
##########################                                ##########################
####################################################################################

Classes to:
        - Generate sample of Multinomial/Dirichlet from an ensemble of categorical law;
        - Fit mixture model over multinomial or dirichlet assumption.

"""


class GenMixtSampleFromCatEns:
    """
    Class to generate sample of Multinomial/Dirichlet from an ensemble of categorical law
    ...

    Attributes
    ----------
    E : int
        Number of categorical ensemble members
    pi_Z : [[float]*K]*M
         M probabilities vector of size K of the multinomial mixture model, M being the number of mixture, and K the number of classes.

    Methods
    -------
    generate(N,distribution="Categorial",**kwargs): Function to generate sample for categorical, multinomial or dirichlet distributions.
        N : int
            Sample size
        distribution : str
            Name of the distribution to generate
        **kwargs: [object]
            Array of function attributes needed for each distribution.
            
    Categorial(N,pi=None,Z=None,seed=12)
        N : int
            Sample size
        pi : [float]*M
            Mixture probabilities vector of size M
        Z : [int]*N
            Mixture labels array
        seed : int
            Random generator seed
            
    Multinomial(self,N,Z=None,pi=None,seed=12)
        N : int
            Sample size
        pi : [float]*M
            Mixture probabilities vector of size M
        Z : [int]*N
            Mixture labels array
        seed : int
            Random generator seed
            
    Dirichlet(N,alpha=None,Z=None,pi=None,seed=12)
        N : int
            Sample size
        alpha: [[float]*K]*M
            Dirichlet parameter vector of size K for each of the M mixture.
        pi : [float]*M
            Mixture probabilities vector of size M
        Z : [int]*N
            Mixture labels array
        seed : int
            Random generator seed
    """
    
    
    def __init__(self,E,pi_Z):
        """
        @param E:int, Number of categorical ensemble members
        @param pi_Z: [[float]*K]*M,  M probabilities vector of size K of the multinomial mixture model, M being the number of mixture, and K the number of classes.
        """
        
        self.E = E
        self.pi_Z = pi_Z
           
    def generate(self,N,distribution="Categorial",**kwargs):
        """
        @param N:int, Sample size
        @param distribution: str, Name of the distribution to generate
        @param **kwargs:[object], Array of function attributes needed for each distribution.
        
        @return: sample array [[float]*E]*N if Categorical distribution is called , else [[float]*K]*N
        """
        self.distribution = distribution
        generator = getattr(self, self.distribution)
        return generator(N=N,**kwargs)
        
    
    def Categorial(self,N,pi=None,Z=None,seed=12):
        """
        @param N : int, Sample size
        @param pi : [float]*M,  Mixture probabilities vector of size M
        @param Z : [int]*N, Mixture labels array
        @param seed : int, Random generator seed
        
        @return: sample array [[float]*E]*N 
        """
        pi_Z = self.pi_Z
        E = self.E
        M = pi_Z.shape[0]
        K = pi_Z.shape[1]
        
        rng = np.random.default_rng(seed)
        list_rng = [np.random.default_rng(i) for i in rng.integers(0,2**31,size=N)]

        
        assert pi_Z.shape[0] == M , "pi_Z rows don't match with M"
        assert pi_Z.shape[1] == K , "pi_Z columns don't match with K"
        assert sum(pi_Z.sum(axis=1)) == M , "pi_Z columns sum != 1"
        if Z is None:
            if pi is None:
                pi = np.array([1/M]*M)
            Z = np.argmax(rng.multinomial(1, pi, size=N),axis=1)
        X = np.zeros((N,self.E))
        for m in range(M):
            ind = np.where(Z==m)[0]
            for n in ind:
                X[n,:] = np.argmax(list_rng[n].multinomial(1, pi_Z[m,:], size=self.E),axis=1)
        return X,Z
    
    def Multinomial(self,N,Z=None,pi=None,seed=12):
        """
        @param N : int, Sample size
        @param pi : [float]*M,  Mixture probabilities vector of size M
        @param Z : [int]*N, Mixture labels array
        @param seed : int, Random generator seed
        
        @return: sample array [[float]*K]*N
        """
        pi_Z = self.pi_Z
        E = self.E
        M = pi_Z.shape[0]
        K = pi_Z.shape[1]
        
        rng = np.random.default_rng(seed)
        
        assert pi_Z.shape[0] == M , "pi_Z rows don't match with M"
        assert pi_Z.shape[1] == K , "pi_Z columns don't match with K"
        assert sum(pi_Z.sum(axis=1)) == M , "pi_Z columns sum != 1"
        
        if Z is None:
            if pi is None:
                pi = np.array([1/M]*M)
            Z = np.argmax(rng.multinomial(1, pi, size=N),axis=1)

        X,Z = self.Categorial(N=N,Z=Z,seed=seed)
        X,classes = aggregate_raters(X)
        
        return X,Z
    
    def Dirichlet(self,N,alpha=None,Z=None,pi=None,seed=12):
        """
        @param N : int, Sample size
        @param alpha: [[float]*K]*M, Dirichlet parameter vector of size K for each of the M mixture.
        @param pi : [float]*M,  Mixture probabilities vector of size M
        @param Z : [int]*N, Mixture labels array
        @param seed : int, Random generator seed
        
        @return: sample array [[float]*K]*N
        """
        pi_Z = self.pi_Z
        E = self.E
        M = pi_Z.shape[0]
        K = pi_Z.shape[1]
        rng = np.random.default_rng(seed)
        
        assert pi_Z.shape[0] == M , "p rows don't match with M"
        assert pi_Z.shape[1] == K , "p columns don't match with K"
        assert sum(pi_Z.sum(axis=1)) == M , "p columns sum != 1"
        
        if Z is None:
            if pi is None:
                pi = np.array([1/M]*M)
            Z = np.argmax(rng.multinomial(1, pi, size=N),axis=1)
        
        if alpha is None:
            X,Z = self.Multinomial(N=N,Z=Z,seed=seed)

            return X/self.E,Z
        else:
            X = np.zeros((T,K))
            for m in range(M):
                ind = np.where(Z==m)[0]
                samp = np.random.dirichlet(alpha[m,:],size=(len(ind)))
                X[ind,:] = samp
            return X,Z
        
    
class Model:
    """
    Class to generate sample of Multinomial/Dirichlet from an ensemble of categorical law
    ...

    Attributes
    ----------
    verbose:
    M:
    E:
    theta_i1:
    model_init:
    threshold:

    Methods
    -------
    KMeans(self,X,M,seed=12,**kwargs):
    smallEM(self,X,M, maxEM=50,init="k-means++"):
    searchM(self,X,seed=12,**kwargs):
    initMMM(self,X,**kwargs):
    fit(self,X,tol=1e-6,maxiter=10,**kwargs):
    predict(self,X):
    predict_proba(self,X):
    """
        
    def __init__(self,U2dist,**kwargs):
        self.verbose = kwargs.get("verbose", 0)
        self.M = kwargs.get("M", None)
        self.E = kwargs.get("E", None)
        self.theta_i1=None
        self.model_init = kwargs.get("model_init", None)
        self.threshold = kwargs.get("threshold", None)
        self.SClist = None
        self.U2dist = U2dist
        
    def KMeans(self,X,M,seed=12,**kwargs):
        init = kwargs.get("init", "k-means++")
        max_iter = kwargs.get("max_iter", 100)
        
        np.random.seed(seed)
        model_init = skc.MiniBatchKMeans(init=init,n_clusters=M,max_iter=max_iter).fit(X)
        
        p_ij = OneHotEncoder(handle_unknown='ignore').fit_transform(model_init.labels_[np.newaxis].T).toarray()
        model = self.params_init(X,p_ij)
        
        
        model = {"KMeans": model_init,
                 "p_ij": p_ij,
                 "theta_i":model["theta_i"]}
        return model
    
    def smallEM(self,X,M, maxEM=50,init="k-means++"):
        list_seed = []
        list_model = []
        list_model_init = []
        list_BIC = []
        for l in range(maxEM):
            seed = np.random.randint(0,1e6)
            self.model_init = self.KMeans(X ,M=M, max_iter = 1,seed=seed,init=init)
            self.fit(X,maxiter=5,M=self.M)
            nuM = self.M+self.M*self.K
            BIC_m = self.BIC(X,self.model["theta_i"],nuM=nuM)
            
            list_seed.append(seed)
            list_model_init.append(self.model_init)
            list_model.append(self.model)
            list_BIC.append(BIC_m)
        
        list_BIC = np.array(list_BIC)
        bestM = np.where(min(list_BIC)==list_BIC)[0][0]
        model = list_model[bestM]
        model["Init"] = list_model_init[bestM]
        model["Seed"] = list_seed
        return {"Model":model, "BIC":list_BIC[bestM]}
    
    def searchTreshold(self,X,end=0.01):
        self.K = X.shape[1]
        
        if self.U2dist == "unlikeability":
            if sum(X[0,:])==self.E:
                u2 = ((X/self.E)*(1-X/self.E)).sum(axis=1)
            else:
                u2 = ((X)*(1-X)).sum(axis=1)
        
        if self.U2dist == "margin":
            if sum(X[0,:])==self.E:
                p = (X/self.E)
                p.sort(axis=1)
                u2 = 1-(p[:,X.shape[1]-1]-p[:,X.shape[1]-2])
            else:
                p = X.copy()
                p.sort(axis=1)
                u2 = 1-(p[:,X.shape[1]-1]-p[:,X.shape[1]-2])


        listthreshold = np.arange(0,np.quantile(u2,1).round(1)+end,end).round(2)


        clusters = self.predict(X,supracluster=False)

        dU2array = []
        for threshold in listthreshold:
            dU2array.append(self.dU2(u2,clusters,threshold=threshold))
        dU2array = np.array(dU2array)
        self.threshold = listthreshold[np.where(dU2array==dU2array.max())[0][0]]
        self.dU2max = dU2array.max()
        
        



    def searchM(self,X,seed=12,**kwargs):
        if self.M is None:
            M = kwargs.get("M", None)
        else:
            M = self.M
        self.K = X.shape[1]
        
        method = kwargs.get("method", "K-means")
        init = kwargs.get("init", "k-means++")
        max_iter = kwargs.get("max_iter", 100)
        maxEM = kwargs.get("maxEM", 50)
        verbose = kwargs.get("verbose", 0)
        np.random.seed(seed)
        if M is None:
            listM = range(2,int(X.shape[0]**0.3))
        else:
            self.M = M
        inertia = 0
        sil = []
        if method=="K-means":
            if isinstance(M, int):
                model_init = skc.MiniBatchKMeans(n_clusters=M,init=init,max_iter=max_iter).fit(X)
#                 sil = silhouette_score(X, model_init.labels_, metric = 'euclidean')
                inertia = model_init.inertia_
                p_ij = OneHotEncoder(handle_unknown='ignore').fit_transform(model_init.labels_[np.newaxis].T).toarray()
                model = self.params_init(X,p_ij)
                nuM = self.M+self.M*self.K
                BIC_m = self.BIC(X,model["theta_i"],nuM=nuM)
                list_BIC =BIC_m
                
            else:
                model_list = []
                
                list_BIC = []
                for m in listM:
                    self.M=m
                    nuM = self.M+self.M*self.K
                    mod = skc.MiniBatchKMeans(n_clusters=m,init=init,max_iter=max_iter).fit(X)
                    model_list.append(mod)
                    p_ij = OneHotEncoder(handle_unknown='ignore').fit_transform(mod.labels_[np.newaxis].T).toarray()
                    model = self.params_init(X,p_ij)
                    BIC_m = self.BIC(X,model["theta_i"],nuM=nuM)
                    list_BIC.append(BIC_m)
#                     sil.append(silhouette_score(X, mod.labels_, metric = 'euclidean'))
                list_BIC=np.array(list_BIC)
                inertia = np.array([i.inertia_ for i in model_list])
#                 sil = np.array(sil)
#                 i=np.where(max(sil)==sil)[0][0]
                i=np.where(min(list_BIC)==list_BIC)[0][0]
                while len(set(model_list[i].labels_)) != listM[i]:
                    i-=1
                model_init = model_list[i]
                M = listM[i]
            self.M = M
            self.modelsave = model_init
            p_ij = OneHotEncoder(handle_unknown='ignore').fit_transform(model_init.labels_[np.newaxis].T).toarray()
            model = self.params_init(X,p_ij)
            theta_i = model["theta_i"]
            model_init = self.E_step(X,theta_i)
            return model_init, (inertia, sil, list_BIC)
        
        if method=="smallEM":
            if isinstance(M, int):
                model_init = self.smallEM(X,M=M,)
                list_BIC = model_init["BIC"]
            else:
                model_list = []
                for m in listM:
                    self.M=m
                    model_list.append(self.smallEM(X,M=m,init=init,maxEM=maxEM))
                
                list_BIC = np.array([i["BIC"] for i in model_list])
                bestM = np.where(min(list_BIC)==list_BIC)[0][0]
                self.M = listM[bestM]
                model_init = model_list[bestM]
                return model_init["Model"], list_BIC
            
    
    def initMMM(self,X,**kwargs):
        self.K = X.shape[1]
        model, criteria = self.searchM(X,**kwargs)
        self.model_init = model
        self.model_init["list_criteria"] = criteria

        
    def fit(self,X,tol=1e-6,maxiter=10,**kwargs):
        
        
        self.K = X.shape[1]
        solver = kwargs.get("solver","Max")
        if self.model_init is None:
            self.initMMM(X,**kwargs)

        theta_i = self.model_init["theta_i"]
        
        if self.verbose>0:
            print("Init: loglike= %s" %(self.loglikelihood(X,theta_i)))
        
        theta_i1 = theta_i.copy()
        self.theta_i = theta_i.copy()
        epsilon = 1e6
        iter_ = 0
        self.model = self.E_step(X,theta_i)
        if np.isnan(self.loglikelihood(X,theta_i)):
            if self.verbose>0:
                print("Nan loglikelihood")
            return
        
        while ((epsilon > tol) and (iter_ < maxiter)):
            self.model = self.E_step(X,theta_i)
            
            p_ij = self.model["p_ij"]

            
            if solver=="Max":
                self.model = self.M_step(X,p_ij)
            if solver=="SGD":
                pass
            
            self.theta_i = self.model["theta_i"].copy()
            
            if np.isnan(self.loglikelihood(X,theta_i1)):
                if self.verbose>0:
                    print("Nan loglikelihood -> break")
                break
            epsilon = self.criteria(X,self.theta_i,theta_i1)
            
            if tol>=abs(epsilon):
                if self.verbose>0:
                    print("Convergence tol reached -> End")
                break
            
            if epsilon < 0:
                self.model["theta_i"] = self.theta_i
                if self.verbose>0:
                    print("Loglike_i1-Loglike_i <0 = Deterioration -> End")
                break
            iter_ +=1
            
            theta_i1 = self.model["theta_i"].copy()
            if self.verbose>0:
                print("Iter: %s, loglike= %s" %(iter_,self.loglikelihood(X,theta_i1)))

        
        
    
    def predict(self,X,supracluster=True):
        if supracluster:
            self.SClist
            temp = self.E_step(X,self.model["theta_i"])


            supracluster = []
            for c in temp["clusters"]:
                supracluster.append(c in self.SClist[0])
            return np.array([supracluster,temp["clusters"]]).T
        else:
            temp = self.E_step(X,self.model["theta_i"])
            return temp["clusters"]

    def predict_proba(self,X):
        temp = self.E_step(X,self.model["theta_i"])
        return temp["p_ij"]
    
    
    def E_step(self,X,theta_i):
        M = len(theta_i["pi"])
        p_ij = np.zeros((X.shape[0],M))
        pMMM = np.zeros(X.shape[0])
        for m in range(M):
            pMMM += theta_i["pi"][m]*self.XZdensity(X,theta_i["theta_i_m"][m,:])
        
        for m in range(M):
            pMMMZ = theta_i["pi"][m]*self.XZdensity(X,theta_i["theta_i_m"][m,:])
            p_ij[:,m] = pMMMZ/pMMM
        
        if sum(np.isnan(p_ij.max(axis=0)))>0:
            for m in np.where(np.isnan(p_ij.max(axis=0)))[0]:
                p_ij[np.where(np.isnan(p_ij[:,m]))[0],m]=1
        labels = p_ij.argmax(axis=1)
        model = {"clusters": labels,
                  "p_ij":p_ij,
                  "theta_i":theta_i}

        return model
    
    def M_step(self,X,p_ij):
        pass
    def params_init(self,X,p_ij):
        pass
    
    def XZdensity(self,X,theta_i,**kwargs):
        pass
    
    def criteria(self,X,theta_i,theta_i1,criteria="loglike"):
        if criteria == "loglike":
            llli = self.loglikelihood(X,theta_i)
            llli1 = self.loglikelihood(X,theta_i1)
            return (llli-llli1)
    
    def loglikelihood(self,X,theta_i,**kwargs):
        lll = 0
        for m in range(len(theta_i["pi"])):
            lll += theta_i["pi"][m]*self.XZdensity(X,theta_i["theta_i_m"][m,:],**kwargs)
        lll[lll==0]=1e-10
        lll[lll==np.Inf]=1
        return sum(np.log(lll))
    
    def BIC(self,X,theta_i,nuM,**kwargs):
        if np.isnan(self.loglikelihood(X,theta_i,**kwargs)):
            return 1e10
        else:
            BIC_m = -2*(self.loglikelihood(X,theta_i,**kwargs))+nuM*np.log(X.shape[0])
            return BIC_m

    def dU2(self,u2,clusters,threshold=0):
        Sclusters =clusters 	
        Sk = np.array(list(range(len(self.model["theta_i"]["pi"]))))
        u2p = []
        
        if self.U2dist == "unlikeability":
            for p in self.model["theta_i"]["theta_i_m"]:
                u2p.append((1-sum(p**2)))
        
        if self.U2dist == "margin":
            for p in self.model["theta_i"]["theta_i_m"]:
                ptmp = p.copy()
                ptmp.sort()
                u2p.append((1-(ptmp[len(ptmp)-1]-ptmp[len(ptmp)-2])))
        
        
        u2p = np.array(u2p)

        ub = u2p[u2p<threshold]
        sb = Sk[u2p<threshold]
        up = u2p[u2p>=threshold]
        sp = Sk[u2p>=threshold]

        Su = Sclusters.copy()
        if len(sb)>0:
            for s in sb:
                Su[Sclusters==s] = 0
            ubm = u2[Su==0].mean()
            ubv = u2[Su==0].var()
            ubmm = ub.mean()
            
        if len(sp)>0:
            for s in sp:
                Su[Sclusters==s] = 1
            upm = u2[Su==1].mean()
            upv = u2[Su==1].var()
            upmm = up.mean()
            
        if len(sb)==0:
            ubm = upm
            ubv = 0
            upmm = up.mean()
            ubmm = upmm

        if len(sp)==0:
            upm = ubm
            upv = 0
            ubmm = ub.mean()
            upmm = ubmm
            
        Nb = sum(Su==0)
        Np = sum(Su==1)
    #                 print(M,threshold,upv,ubv,((Np-1)*upv+(Nb-1)*ubv))
        
        if np.isnan(upv):
            upv=0
        if np.isnan(ubv):
            ubv=0
        
        if (upv==0)&(ubv==0):
            dU2 = 0
        else:
            dU2 = abs(ubm-upm)/np.sqrt(((Np-1)*upv+(Nb-1)*ubv))
        return dU2


class MixtMultinomial(Model):
    def __init__(self,E=10,**kwargs):
        super().__init__(**kwargs)
        self.E = E
        self.M = kwargs.get("M", None)
        self.K = kwargs.get("K", None)
        
    def XZdensity(self,X,theta_i_m,**kwargs):
        return multinomial(self.E,theta_i_m).pmf(X)
    
    def params_init(self,X,p_ij):
        return self.M_step(X,p_ij)
        
    
    def M_step(self,X,p_ij):
        self.E = sum(X[0,:])
        M = p_ij.shape[1]
        labels = p_ij.argmax(axis=1)
        theta_i = {"pi":[],"theta_i_m":[]}
        for m in range(M):
            p_ij_tab = np.tile(p_ij[:,m][np.newaxis].T,X.shape[1])
            sumK = p_ij[:,m].sum(axis=0)
            if sumK == 0:
                sumK = 1e-10
            theta_i["theta_i_m"].append((X*p_ij_tab).sum(axis=0)/(sumK*self.E))
            theta_i["pi"].append(sum(p_ij[:,m])/X.shape[0])


        theta_i["theta_i_m"] = np.array(theta_i["theta_i_m"])
        theta_i["pi"] = np.array(theta_i["pi"])
        
        model = {"clusters": labels,
                  "p_ij":p_ij,
                  "theta_i":theta_i}
        return model

    
class MixtDirichlet(Model):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.M = kwargs.get("M", None)
        self.K = kwargs.get("K", None)
    
    def XZdensity(self,X,theta_i_m,**kwargs):
        if X.shape[0] != self.K:
            D_norm = X.T
            for i in range(D_norm.shape[1]):
                tmp = D_norm[:,i]
                D_norm[tmp==0,i] = 1e-10
                D_norm[tmp==1,i] = 1-1e-10
            return dirichlet.pdf(D_norm,theta_i_m)
        else:
            return dirichlet.pdf(X,theta_i_m)
    
    def OptimEMDir(self,sol):
        sol = np.exp(sol)
        self.theta_i["theta_i_m"] = sol.reshape((self.M,self.K))
        c = 0
        for m in range(self.M):
            c += np.log(self.theta_i["pi"][m])*self.theta_i["pi"][m]
        return -(self.loglikelihood(self.D_norm,self.theta_i)+self.mu(self.theta_i["pi"])*c)
    
    def pi_update(self,pi):
        denom = 0
        for m in range(self.M):
            denom += (1+np.log(pi[m]))*pi[m]
        denom = self.p_ij.shape[0]+denom*self.mu(pi)
        num = self.p_ij.sum(axis=0)+self.mu(pi)*(pi*(1+np.log(pi)))
        return num/denom
        
    def mu(self,pi):
        denom = 0
        num = 0
        for m in range(self.M):
            denom += np.log(pi[m])*pi[m]
            num += self.p_ij[:,m]*pi[m]
        
        return num.sum(axis=0)/denom
    
    def params_init(self,X,p_ij):
        labels = p_ij.argmax(axis=1)
        pi = p_ij.sum(axis=0)/sum(p_ij.sum(axis=0))
        theta_i_m = np.ones((self.M,self.K))/self.K
        ind = np.where(labels==0)[0]
        x11prime = X[ind,0].mean()
        x21prime = (X[ind,0]**2).mean()
        for m in range(self.M):
            for k in range(self.K):
                ind = np.where(labels==m)[0]
                x1prime = X[ind,k].mean()
                theta_i_m[m,k] = (x11prime-x21prime)*x1prime/(x21prime-x11prime**2)
                
        theta_i = {"pi":pi,"theta_i_m":theta_i_m}
        model = {"clusters": labels,
                  "p_ij":p_ij,
                  "theta_i":theta_i}
        return model
        
    def M_step(self,X,p_ij):
        self.D_norm = X.T
        for i in range(self.D_norm.shape[1]):
            tmp = self.D_norm[:,i]
            self.D_norm[tmp==0,i] = 1e-10
            self.D_norm[tmp==1,i] = 1-1e-10
        self.M = p_ij.shape[1]
        labels = p_ij.argmax(axis=1)
        
        self.p_ij = p_ij
        self.theta_i1 = self.theta_i

        sol = self.theta_i1["theta_i_m"].reshape(self.M*self.K)
        sol = minimize(self.OptimEMDir, np.log(sol))
        sol = np.exp(sol.x)
        theta_i = {"pi":self.pi_update(self.theta_i1["pi"]),"theta_i_m":sol.reshape((self.M,self.K))}
        model = {"clusters": labels,
                  "p_ij":p_ij,
                  "theta_i":theta_i}
        return model


class MixtModel(Model):
    def __init__(self,distribution,**kwargs):
        super().__init__(**kwargs)
        filename = threshold = kwargs.get("filename",None)
        self.U2dist = kwargs.get("U2dist","unlikeability")
        
        if not filename is None:
            MM = self.load(filename)
            for k in MM.__dict__.keys():
                setattr(self, k, getattr(MM, k))
            del MM
        else:
            self.distributionName = distribution
            if distribution == "Multinomial":
                self.distribution = MixtMultinomial(**kwargs)
                
            if distribution == "Dirichlet":
                self.distribution = MixtDirichlet(**kwargs)
        
            
    def fit(self,X,**kwargs):
        self.M = kwargs.get("M", None)
        self.threshold = kwargs.get("threshold",None)
        kwargs["U2dist"] = self.U2dist
        
        if self.M is None:
            Mmax = int(X.shape[0]**0.3)
            if self.distributionName == "Multinomial":
                listdist = [MixtMultinomial(**kwargs) for i in range(Mmax-1)]
            else:
                listdist = [MixtDirichlet(**kwargs) for i in range(Mmax-1)]
            listBIC = []
            
            for m in range(1,Mmax):
                listdist[m-1].fit(X,M=m,**kwargs)
                nuM = len(listdist[m-1].model["theta_i"]["pi"])+len(listdist[m-1].model["theta_i"]["pi"])*X.shape[1]
                listBIC.append(listdist[m-1].BIC(X,listdist[m-1].model["theta_i"],nuM=nuM))
            listBIC = np.array(listBIC)

            self.distribution = listdist[np.where(listBIC==min(listBIC))[0][0]]
        else:
            self.distribution.fit(X,**kwargs)
        self.model = self.distribution.model
        self.model_init = self.distribution.model_init
        
        pi = self.model["theta_i"]["pi"].copy()

        theta_i_m = self.model["theta_i"]["theta_i_m"].copy()
        order = np.arange(0,theta_i_m.shape[0])
        reorder = np.zeros(theta_i_m.shape[0])
        reorder = reorder.astype(int)
        
        
        for m in range(theta_i_m.shape[0]):
            ind_ = np.where(theta_i_m.max(axis=1)==max(theta_i_m.max(axis=1)))[0]
            if len(ind_)>1:
                pi_temp = pi[ind_]
                reorder[m] = np.argsort(pi_temp)[len(ind_)-1]
            else:
                reorder[m] = ind_
            theta_i_m[reorder[m],:] = 0
            
        reorder = reorder.astype(int)
        
        self.model["theta_i"]["pi"] = self.model["theta_i"]["pi"][reorder]
        self.model["theta_i"]["theta_i_m"] = self.model["theta_i"]["theta_i_m"][reorder,:]
        self.model["theta_i"]["theta_i_m"] = self.model["theta_i"]["theta_i_m"]/(self.model["theta_i"]["theta_i_m"]).sum(axis=1,keepdims=True)
        self.model["clusters"] = np.array([reorder[m] for m in self.model["clusters"]])
        self.model["p_ij"] = self.model["p_ij"][:,reorder]
        
        self.model_init["theta_i"]["pi"] = self.model_init["theta_i"]["pi"][reorder]
        self.model_init["theta_i"]["theta_i_m"] = self.model_init["theta_i"]["theta_i_m"][reorder,:]
        self.model_init["clusters"] = np.array([reorder[m] for m in self.model_init["clusters"]])
        self.model_init["p_ij"] = self.model_init["p_ij"][:,reorder]
        
        self.distribution.model = self.model
        self.distribution.model_init = self.model_init

        if self.threshold is None:
            end = kwargs.get("end", 0.01)
            self.distribution.searchTreshold(X,end=end)
        else:
            self.distribution.threshold = self.threshold

        u2p = []
        if self.U2dist == "unlikeability":
            for p in self.model["theta_i"]["theta_i_m"]:
                u2p.append((1-sum(p**2)))
        
        if self.U2dist == "margin":
            for p in self.model["theta_i"]["theta_i_m"]:
                ptmp = p.copy()
                ptmp.sort()
                u2p.append((1-(ptmp[len(ptmp)-1]-ptmp[len(ptmp)-2])))
        u2p = np.array(u2p)
        
        self.SClist = [np.where(u2p<self.distribution.threshold)[0],np.where(u2p>=self.distribution.threshold)[0]]
        self.distribution.SClist = [np.where(u2p<self.distribution.threshold)[0],np.where(u2p>=self.distribution.threshold)[0]]
        
    def save(self,filename="model.pickle"):
        with open(filename,"wb") as f:
            pickle.dump(self,f)
    
    def load(self,filename):
        with open(filename,"rb") as f:
            MM =  pickle.load(f)
        return MM
    
            

        
if __name__ == "main":
    E = 10
    T = 10000
    seed = 24
    M=3
    K=5
    p_Z = np.array([0.45,0.45,0.1])
    p_Z = np.array([1/M]*M)
    pi_Z = np.array([[0.99,0,0,0,0.01],
                     [0.04,0.9,0.04,0.01,0.01],
                     [0.1,0.1,0.6,0.1,0.1]])
    np.random.seed(12)
    alpha = np.random.rand(3,5)*3

    GenSample = GenMixtSampleFromCatEns(E=E,pi_Z=pi_Z)


    Y,Z = GenSample.generate(T=T,pi=p_Z,seed=seed,distribution="Categorial")
    X_,Z_X = GenSample.generate(T=T,Z=Z,seed=seed,distribution="Multinomial")
    # Dirichlet sample derived from Cat Ensemble
    D,Z_D = GenSample.generate(T=T,Z=Z,seed=seed,distribution="Dirichlet")
    # Dirichlet sample generated from alpha parameter
    Dalpha,Z_D = GenSample.generate(T=T,alpha=alpha,Z=Z,seed=seed,distribution="Dirichlet")
    
    MMM = MixtModel(E=E,distribution="Multinomial")
    MMM.fit(X_,method="K-means",maxEM=50,init="k-means++")
    
    DMM = MixtModel(E=E,distribution="Dirichlet")
    DMM.fit(Dalpha,method="K-means",maxEM=50,init="k-means++")
